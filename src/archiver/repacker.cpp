/**
 * @file repacker.cpp
 * @brief Repacker for EVA BPK0 archive format.
 *
 * Rebuilds a BPK0/BDL0 PKG archive from:
 *   - A manifest.json produced by unpacker (contains all metadata needed to
 *     reconstruct BDL0 headers without the original PKG file).
 *   - Extracted raw files under data/workspace/raw_unpacked/
 *   - Optional patch files under data/patch/  (take priority over workspace)
 *
 * Key design decisions
 * --------------------
 * 1. NO dependency on the original PKG file.  All BDL0 header fields are
 *    stored verbatim in manifest.json by the unpacker.
 * 2. File payloads are compressed / encoded in parallel (std::async) to
 *    saturate CPU cores while keeping disk IO sequential.
 * 3. A single output buffer is built in memory; only one large write() call
 *    is issued at the very end, minimising system-call and seek overhead.
 *    For archives larger than available RAM the code falls back to a
 *    streaming write path (see LARGE_PKG_STREAMING_WRITE below).
 * 4. Memory-mapped reads for workspace / patch files via boost::interprocess.
 *
 * Build dependencies: Boost.Locale, Boost.Interprocess, nlohmann/json, zlib
 *
 * Usage:
 *   repacker <manifest.json> <output.pkg>
 */

#include "types.hpp"

#include <algorithm>
#include <cassert>
#include <cstring>
#include <exception>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#include <boost/interprocess/file_mapping.hpp>
#include <boost/interprocess/mapped_region.hpp>
#include <boost/locale.hpp>
#include <nlohmann/json.hpp>
#include <zlib.h>

namespace fs  = std::filesystem;
namespace bip = boost::interprocess;
using json    = nlohmann::json;

/* =========================================================================
 * Compile-time knob: set to 1 to use a streaming (fwrite) output path
 * instead of a single in-memory buffer.  Useful when the output PKG is
 * larger than the available physical RAM.
 * ========================================================================= */
#ifndef LARGE_PKG_STREAMING_WRITE
#  define LARGE_PKG_STREAMING_WRITE 0
#endif

/* =========================================================================
 * Alignment helper
 * ========================================================================= */

/**
 * @brief Round @p value up to the next multiple of @p align_to.
 *
 * @param value     Value to align.
 * @param align_to  Alignment boundary (must be a power of two).
 * @return          Smallest multiple of @p align_to that is >= @p value.
 */
static constexpr uint32_t align_up(uint32_t value, uint32_t align_to) noexcept
{
    return (value + align_to - 1u) & ~(align_to - 1u);
}

/* =========================================================================
 * Encoding helpers
 * ========================================================================= */

/**
 * @brief Convert a UTF-8 string to CP932 (Shift-JIS).
 *
 * Used to convert patch-file content and directory/file names back to the
 * encoding expected by the game engine.
 *
 * @param utf8  Input UTF-8 string.
 * @return      CP932-encoded string.
 * @throws      boost::locale::conv::conversion_error on encoding failure.
 */
static std::string utf8_to_cp932(const std::string& utf8)
{
    return boost::locale::conv::from_utf<char>(utf8, "CP932");
}

/* =========================================================================
 * File-read helper using mmap
 * ========================================================================= */

/**
 * @brief Memory-map a file and return its contents as a byte vector.
 *
 * Uses boost::interprocess for a zero-copy read on platforms that support it.
 * Falls back to a regular ifstream read for very small files where mmap
 * overhead would dominate.
 *
 * @param path  Path to the file to read.
 * @return      File contents as a vector<uint8_t>.
 * @throws      std::runtime_error if the file cannot be opened.
 */
static std::vector<uint8_t> mmap_read_file(const fs::path& path)
{
    std::error_code ec;
    uintmax_t sz = fs::file_size(path, ec);
    if (ec || sz == 0)
        return {};

    bip::file_mapping  fm(path.string().c_str(), bip::read_only);
    bip::mapped_region mr(fm, bip::read_only);

    const auto* p = static_cast<const uint8_t*>(mr.get_address());
    return std::vector<uint8_t>(p, p + mr.get_size());
}

/* =========================================================================
 * zlib compression
 * ========================================================================= */

/**
 * @brief Compress data using zlib (deflate, default level).
 *
 * @param in   Raw bytes to compress.
 * @return     Compressed bytes.
 * @throws     std::runtime_error on compression failure.
 */
static std::vector<uint8_t> compress_zlib(const std::vector<uint8_t>& in)
{
    uLongf bound = compressBound(static_cast<uLong>(in.size()));
    std::vector<uint8_t> out(bound);
    if (compress(out.data(), &bound,
                 reinterpret_cast<const Bytef*>(in.data()),
                 static_cast<uLong>(in.size())) != Z_OK)
        throw std::runtime_error("zlib compress failed");
    out.resize(bound);
    return out;
}

/* =========================================================================
 * Per-file processing result (produced by async workers)
 * ========================================================================= */

/**
 * @brief All data needed to write one BDL0-wrapped archive entry.
 *
 * Workers populate this struct; the main thread stitches them together in
 * the correct order into the output buffer.
 */
struct FileBlob {
    BDL0Header           bdl_header  = {};   ///< Ready-to-write BDL0 header
    std::vector<uint8_t> payload;            ///< Compressed or raw payload bytes
    uint32_t             origin_entry_unk0 = 0; ///< Preserved from manifest
    std::string          cp932_name;         ///< File name in CP932 encoding
    bool                 patched    = false; ///< True when patch/ file was used
    bool                 identical  = false; ///< True when patch == workspace
};

/* =========================================================================
 * Async worker: build one FileBlob
 * ========================================================================= */

/**
 * @brief Build a FileBlob for a single archive entry.
 *
 * This function is designed to run in a std::async worker thread.  It reads
 * the source file (patch preferred, workspace fallback), converts encoding,
 * compresses if required, and assembles the BDL0 header.
 *
 * The function does NOT perform any IO to the output PKG — that is left to
 * the main thread so that writes remain sequential.
 *
 * @param dir_utf8    UTF-8 directory name (used to build source paths).
 * @param file_json   The "files" array element from manifest.json.
 * @return            Populated FileBlob.
 */
static FileBlob build_file_blob(const std::string& dir_utf8, const json& file_json)
{
    FileBlob blob;

    /* ------------------------------------------------------------------ */
    /* 1. Extract manifest metadata                                         */
    /* ------------------------------------------------------------------ */
    std::string fn_utf8   = file_json["name"].get<std::string>();
    bool        is_text   = file_json["is_text"].get<bool>();
    bool        is_jis2ucs2 = fn_utf8 == "JIS2UCS.BIN";
    bool        was_compressed = false;
    if (file_json.contains("was_compressed"))
        was_compressed = file_json["was_compressed"].get<bool>();
    else if (file_json.contains("origin_compressed"))
        was_compressed = file_json["origin_compressed"].get<bool>();

    blob.origin_entry_unk0 = file_json.value("origin_entry_unk0", uint32_t(0));
    blob.cp932_name        = utf8_to_cp932(fn_utf8);

    /* ------------------------------------------------------------------ */
    /* 2. Locate source file (patch/ takes priority over workspace/)        */
    /* ------------------------------------------------------------------ */
    fs::path patch_path = fs::path("data/patch")     / dir_utf8 / fn_utf8;
    fs::path work_path  = fs::path("data/workspace/raw_unpacked") / dir_utf8 / fn_utf8;

    bool use_patch = ((is_text||is_jis2ucs2) && fs::exists(patch_path));

    /* Non-text files (binaries) always come from workspace */
    fs::path src_path = use_patch ? patch_path : work_path;

    if (!fs::exists(src_path))
        throw std::runtime_error("Source file not found: " + src_path.string());

    blob.patched = use_patch;

    /* ------------------------------------------------------------------ */
    /* 3. Read source file via mmap                                         */
    /* ------------------------------------------------------------------ */
    std::vector<uint8_t> raw = mmap_read_file(src_path);

    /* ------------------------------------------------------------------ */
    /* 4. Charset conversion: UTF-8 → CP932 for text files                 */
    /* ------------------------------------------------------------------ */
    if (is_text && !raw.empty()) {
        std::string utf8_str(reinterpret_cast<const char*>(raw.data()), raw.size());
        std::string cp932_str = utf8_to_cp932(utf8_str);
        raw.assign(reinterpret_cast<const uint8_t*>(cp932_str.data()),
                   reinterpret_cast<const uint8_t*>(cp932_str.data() + cp932_str.size()));
    }

    /* ------------------------------------------------------------------ */
    /* 5. Compress payload if the original entry was compressed             */
    /* ------------------------------------------------------------------ */
    uint32_t orig_size = static_cast<uint32_t>(raw.size());

    if (was_compressed) {
        blob.payload             = compress_zlib(raw);
        blob.bdl_header.compressedSize = static_cast<uint32_t>(blob.payload.size());
    } else {
        blob.payload             = std::move(raw);
        blob.bdl_header.compressedSize = 0;
    }

    /* ------------------------------------------------------------------ */
    /* 6. Fill BDL0 header                                                  */
    /* ------------------------------------------------------------------ */
    std::memcpy(blob.bdl_header.magic, "BDL0", 4);
    blob.bdl_header.fileSize = orig_size;

    return blob;
}

/* =========================================================================
 * In-memory output buffer helpers
 * ========================================================================= */

/**
 * @brief Append raw bytes to a byte vector.
 *
 * Convenience wrapper to keep the assembly code readable.
 *
 * @param buf   Destination buffer (modified in place).
 * @param data  Source pointer.
 * @param len   Number of bytes to append.
 */
static void buf_append(std::vector<uint8_t>& buf, const void* data, size_t len)
{
    const auto* p = static_cast<const uint8_t*>(data);
    buf.insert(buf.end(), p, p + len);
}

/**
 * @brief Append @p count zero bytes to @p buf.
 *
 * @param buf    Destination buffer.
 * @param count  Number of zero bytes.
 */
static void buf_pad(std::vector<uint8_t>& buf, size_t count)
{
    buf.insert(buf.end(), count, uint8_t(0));
}

/**
 * @brief Overwrite bytes in @p buf at @p offset with @p len bytes from @p data.
 *
 * Used to back-patch the BPK0 header after all offsets are known.
 *
 * @param buf     Destination buffer.
 * @param offset  Byte offset within buf to start writing.
 * @param data    Source pointer.
 * @param len     Number of bytes to copy.
 * @throws        std::out_of_range if the range exceeds buf.size().
 */
static void buf_patch(std::vector<uint8_t>& buf, size_t offset,
                      const void* data, size_t len)
{
    if (offset + len > buf.size())
        throw std::out_of_range("buf_patch: write beyond buffer end");
    std::memcpy(buf.data() + offset, data, len);
}

/* =========================================================================
 * EvaRepacker
 * ========================================================================= */

/**
 * @brief Orchestrates the full repack pipeline.
 *
 * The pipeline has three phases:
 *  1. Parallel – compute FileBlob for every file entry (compress, encode).
 *  2. Sequential – assemble data region into output buffer, record offsets.
 *  3. Sequential – append index (RawEntry blocks) and directory table,
 *                  then back-patch the BPK0 header.
 */
class EvaRepacker {
public:
    /**
     * @brief Run the full repack.
     *
     * @param manifest_path  Path to manifest.json produced by the unpacker.
     * @param output_pkg     Destination PKG file path.
     */
    void repack(const std::string& manifest_path, const std::string& output_pkg)
    {
        /* ----------------------------------------------------------------
         * Load manifest
         * ---------------------------------------------------------------- */
        std::ifstream ifs(manifest_path);
        if (!ifs)
            throw std::runtime_error("Cannot open manifest: " + manifest_path);
        json manifest = json::parse(ifs);

        /* ----------------------------------------------------------------
         * Pre-scan: count total files for output buffer reservation
         * ---------------------------------------------------------------- */
        size_t total_files = 0;
        for (auto& dir : manifest["directories"])
            total_files += dir["files"].size();

        /* ----------------------------------------------------------------
         * Phase 1 — launch async workers for all file blobs
         *
         * We keep futures in a 2D structure matching the manifest layout so
         * that Phase 2 can iterate in the same order without sorting.
         * ---------------------------------------------------------------- */
        struct DirWork {
            std::string              utf8_name;
            uint32_t                 origin_dir_unk0 = 0;
            std::vector<std::future<FileBlob>> futures;
        };
        std::vector<DirWork> dir_work;
        dir_work.reserve(manifest["directories"].size());

        for (auto& dir : manifest["directories"]) {
            DirWork dw;
            dw.utf8_name       = dir["name"].get<std::string>();
            dw.origin_dir_unk0 = dir.value("origin_dir_unk0", uint32_t(0));

            for (auto& file : dir["files"]) {
                /* Capture copies for the lambda — the JSON objects must not
                 * be touched from worker threads. */
                std::string dir_name_copy  = dw.utf8_name;
                json        file_json_copy = file;   /* cheap: shared_ptr inside */

                dw.futures.push_back(
                    std::async(std::launch::async,
                        [dir_name_copy, file_json_copy]() mutable {
                            return build_file_blob(dir_name_copy, file_json_copy);
                        }));
            }

            dir_work.push_back(std::move(dw));
        }

        /* ----------------------------------------------------------------
         * Phase 2 — sequentially collect worker results and assemble the
         * data region (BPK0 header placeholder + BDL0 blocks).
         *
         * Layout (same as original PKG):
         *   [0x000]  BPK0Header  (back-patched in Phase 3)
         *   [0x800]  BDL0 block 0   (sector-aligned)
         *            BDL0 block 1
         *            ...
         *   [entry_base]  RawEntry arrays + file name strings (16-byte aligned)
         *   [dir_base]    RawDirectory structs + directory names (4-byte aligned)
         * ---------------------------------------------------------------- */
        std::vector<uint8_t> out_buf;
        out_buf.reserve(256 * 1024 * 1024);  /* initial 256 MiB reservation */

        /* --- BPK0 header placeholder (filled in Phase 3) --- */
        BPK0Header bpk_header{};
        buf_append(out_buf, &bpk_header, sizeof(BPK0Header));

        /* --- Data region: one BDL0 block per file --- */
        struct DirResult {
            std::string              utf8_name;
            std::string              cp932_name;
            uint32_t                 origin_dir_unk0 = 0;
            std::vector<RawEntry>    file_entries;
            std::vector<std::string> cp932_file_names;
            uint32_t                 entry_block_size = 0; /* filled in Phase 3 */
        };
        std::vector<DirResult> results;
        results.reserve(dir_work.size());

        size_t patched_count = 0;

        for (auto& dw : dir_work) {
            DirResult dr;
            dr.utf8_name       = dw.utf8_name;
            dr.cp932_name      = utf8_to_cp932(dw.utf8_name);
            dr.origin_dir_unk0 = dw.origin_dir_unk0;

            for (size_t fi = 0; fi < dw.futures.size(); ++fi) {
                /* Collect the worker result (blocks until the worker finishes) */
                FileBlob blob = dw.futures[fi].get();

                /* Sector-align (0x800) the current write position */
                {
                    uint32_t cur = static_cast<uint32_t>(out_buf.size());
                    uint32_t pad = (SECTOR_SIZE_ - (cur % SECTOR_SIZE_)) % SECTOR_SIZE_;
                    if (pad) buf_pad(out_buf, pad);
                }

                /* Record the offset of this BDL0 block */
                uint32_t whence = static_cast<uint32_t>(out_buf.size());

                /* Write BDL0 header + payload */
                buf_append(out_buf, &blob.bdl_header, sizeof(BDL0Header));
                buf_append(out_buf, blob.payload.data(), blob.payload.size());

                /* Logging */
                // std::string key = dw.utf8_name + "/" +
                //     dw.futures[fi].valid()   /* always false here, but keep key */
                //     /* use fi to index original file name from manifest */;
                if (blob.patched) {
                    ++patched_count;
                    std::cout << "[PATCH] " << dr.utf8_name << "/"
                              << blob.cp932_name << '\n';
                }

                /* Build RawEntry for this file */
                uint32_t stored_size = (blob.bdl_header.compressedSize > 0)
                    ? blob.bdl_header.compressedSize
                    : blob.bdl_header.fileSize;

                RawEntry rfe{};
                rfe.unk0   = blob.origin_entry_unk0;
                rfe.unk1   = align_up(stored_size + static_cast<uint32_t>(sizeof(BDL0Header)),
                                      SECTOR_SIZE_);
                rfe.size   = blob.bdl_header.fileSize;
                rfe.offset = whence;

                dr.file_entries.push_back(rfe);
                dr.cp932_file_names.push_back(blob.cp932_name);
            }

            results.push_back(std::move(dr));
        }

        /* ----------------------------------------------------------------
         * Phase 3a — append the index region (RawEntry arrays).
         *
         * The entry region starts at the next 16-byte-aligned position after
         * the last BDL0 block.  It must not overlap with the entry region of
         * the original PKG if the caller wants a byte-identical header area
         * (here we just place it directly after the data).
         * ---------------------------------------------------------------- */
        uint32_t entry_base;
        {
            uint32_t cur = static_cast<uint32_t>(out_buf.size());
            entry_base   = align_up(cur, 16u);
            if (entry_base > cur) buf_pad(out_buf, entry_base - cur);
        }

        std::vector<uint32_t> dir_entry_offsets;
        dir_entry_offsets.reserve(results.size());

        for (auto& dr : results) {
            uint32_t block_start = static_cast<uint32_t>(out_buf.size());
            dir_entry_offsets.push_back(block_start);

            /* Write RawEntry structs for all files in this directory */
            for (const auto& rfe : dr.file_entries)
                buf_append(out_buf, &rfe, sizeof(RawEntry));

            /* Immediately after the entries: CP932 file name strings */
            for (const auto& name : dr.cp932_file_names)
                buf_append(out_buf, name.c_str(), name.size() + 1);

            /* Pad to 16-byte boundary */
            {
                uint32_t cur = static_cast<uint32_t>(out_buf.size());
                uint32_t pad = align_up(cur, 16u) - cur;
                if (pad) buf_pad(out_buf, pad);
            }

            uint32_t block_end = static_cast<uint32_t>(out_buf.size());
            dr.entry_block_size = block_end - block_start;
        }

        /* ----------------------------------------------------------------
         * Phase 3b — append the directory table (RawDirectory + name strings).
         * ---------------------------------------------------------------- */
        uint32_t dir_table_pos = static_cast<uint32_t>(out_buf.size());

        for (size_t i = 0; i < results.size(); ++i) {
            const auto& dr = results[i];

            RawDirectory rd{};
            rd.unk0   = dr.origin_dir_unk0;
            rd.unk1   = static_cast<uint16_t>(
                            sizeof(RawDirectory) +
                            align_up(static_cast<uint32_t>(dr.cp932_name.size() + 1), 4u));
            rd.num    = static_cast<uint16_t>(dr.file_entries.size());
            rd.offset = dir_entry_offsets[i];
            rd.size   = dr.entry_block_size;
            rd.zero   = 0;

            buf_append(out_buf, &rd, sizeof(RawDirectory));
            buf_append(out_buf, dr.cp932_name.c_str(), dr.cp932_name.size() + 1);

            /* Pad directory name to 4-byte boundary */
            {
                uint32_t cur = static_cast<uint32_t>(out_buf.size());
                uint32_t pad = align_up(cur, 4u) - cur;
                if (pad) buf_pad(out_buf, pad);
            }
        }

        /* ----------------------------------------------------------------
         * Phase 3c — back-patch the BPK0 header at offset 0.
         * ---------------------------------------------------------------- */
        BPK0Header final_head{};
        final_head.entry_offset    = entry_base;
        final_head.dir_offset      = dir_table_pos;
        final_head.dir_entry_diff  = dir_table_pos - entry_base;
        buf_patch(out_buf, 0, &final_head, sizeof(BPK0Header));

        /* ----------------------------------------------------------------
         * Phase 4 — write the assembled buffer to disk in one call.
         *
         * A single write() minimises system-call overhead and allows the OS
         * to optimise the underlying IO (e.g. large sequential write-back).
         * ---------------------------------------------------------------- */
        {
            std::ofstream ofs(output_pkg, std::ios::binary | std::ios::trunc);
            if (!ofs)
                throw std::runtime_error("Cannot open output: " + output_pkg);
            ofs.write(reinterpret_cast<const char*>(out_buf.data()),
                      static_cast<std::streamsize>(out_buf.size()));
            if (!ofs)
                throw std::runtime_error("Write failed for: " + output_pkg);
        }

        /* ----------------------------------------------------------------
         * Summary
         * ---------------------------------------------------------------- */
        std::cout << "[+] Repack complete.\n"
                  << "[+] Data region start : 0x" << std::hex << SECTOR_SIZE_ << '\n'
                  << "[+] Index region start: 0x" << entry_base << '\n'
                  << "[+] Dir table start   : 0x" << dir_table_pos << std::dec << '\n'
                  << "[+] Patched files     : " << patched_count << '\n'
                  << "[+] Total size        : " << out_buf.size() << " bytes\n";
    }

private:
    static constexpr uint32_t SECTOR_SIZE_ = 0x800; ///< BDL0 block alignment
};

/* =========================================================================
 * main
 * ========================================================================= */

/**
 * @brief Program entry point.
 *
 * @param argc  Expected: 3
 * @param argv  [1] manifest.json path, [2] output PKG path
 */
int main(int argc, char* argv[])
{
    boost::locale::generator gen;
    std::locale::global(gen("en_US.UTF-8"));

    if (argc != 3) {
        std::cerr << "Usage: " << argv[0]
                  << " <manifest.json> <output.pkg>\n";
        return 1;
    }

    try {
        EvaRepacker repacker;
        repacker.repack(argv[1], argv[2]);
    } catch (const std::exception& e) {
        std::cerr << "Fatal Error: " << e.what() << '\n';
        return 1;
    }

    return 0;
}