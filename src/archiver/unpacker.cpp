/**
 * @file unpacker.cpp
 * @brief Unpacker for EVA BPK0 archive format (NEVA.PKG).
 *
 * This tool memory-maps the input PKG file for zero-copy reads, extracts
 * each BDL0-wrapped entry (decompressing zlib payloads when needed),
 * converts CP932 text files to UTF-8, and emits a manifest.json that
 * contains every field required by the repacker — so the original PKG
 * file is NOT needed during repacking.
 *
 * Build dependencies: Boost.Locale, Boost.Interprocess, nlohmann/json, zlib
 *
 * Usage:
 *   unpacker <pkg_file> <dir_table_offset_hex> <dir_count> <output_root>
 *
 * Example:
 *   unpacker data/raw/NEVA.PKG 0x12242C10 345 data/workspace/raw_unpacked
 */

#include "types.hpp"

#include <algorithm>
#include <cctype>
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
 * Encoding helpers
 * ========================================================================= */

/**
 * @brief Convert a raw CP932 byte string to UTF-8.
 *
 * Uses boost::locale with the "skip" error policy so that stray bytes in
 * binary-ish filenames do not abort the process.
 *
 * @param raw  Raw CP932 bytes (null-terminated C++ string).
 * @return     UTF-8 string, or "encoding_error" on catastrophic failure.
 */
static std::string cp932_to_utf8(const std::string& raw)
{
    try {
        return boost::locale::conv::to_utf<char>(
            raw, "CP932", boost::locale::conv::skip);
    } catch (...) {
        return "encoding_error";
    }
}

/* =========================================================================
 * Text normalisation helpers
 * ========================================================================= */

/**
 * @brief Normalise line endings to CRLF.
 *
 * The function first strips any stray CR characters (converting bare CR to LF
 * and collapsing existing CRLF sequences) and then re-inserts CRLF pairs for
 * every LF, matching the original file's line-ending convention.
 *
 * @param s  Input string (arbitrary line endings).
 * @return   String with canonical CRLF line endings.
 */
static std::string normalize_to_crlf(const std::string& s)
{
    /* --- Pass 1: collapse to bare LF --- */
    std::string lf;
    lf.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        char c = s[i];
        if (c == '\r') {
            /* Skip the CR of a CRLF pair; convert bare CR → LF */
            if (i + 1 < s.size() && s[i + 1] == '\n')
                continue;           /* the LF will be handled on next iteration */
            lf.push_back('\n');
        } else {
            lf.push_back(c);
        }
    }

    /* --- Pass 2: expand LF → CRLF --- */
    std::string out;
    out.reserve(lf.size() + lf.size() / 16);
    for (char c : lf) {
        if (c == '\n') {
            out.push_back('\r');
            out.push_back('\n');
        } else {
            out.push_back(c);
        }
    }
    return out;
}

/* =========================================================================
 * Bounds-checking helper
 * ========================================================================= */

/**
 * @brief Assert that [offset, offset+len) lies within the mapped region.
 *
 * @throws std::out_of_range if the range exceeds the mapped size.
 */
static void check_bounds(size_t mapped_size, size_t offset, size_t len,
                          const char* context)
{
    if (offset + len > mapped_size)
        throw std::out_of_range(std::string("out-of-bounds access in ") + context);
}

/* =========================================================================
 * File-record definition used between worker threads and the collector
 * ========================================================================= */

/**
 * @brief All data produced for a single archive entry.
 *
 * Worker threads populate these structs; the main thread serialises them
 * to disk and appends them to the manifest — keeping the hot path lock-free
 * for the expensive decompress + encode work.
 */
struct FileRecord {
    std::string  dir_utf8;          ///< Directory name in UTF-8
    std::string  file_utf8;         ///< File name in UTF-8
    fs::path     save_path;         ///< Absolute destination path
    std::vector<uint8_t> payload;   ///< Final bytes to write to disk
    bool         is_text       = false;
    bool         was_compressed = false;
    uint32_t     origin_entry_unk0  = 0;
    uint32_t     origin_entry_unk1  = 0;
    uint32_t     origin_entry_size  = 0;
    uint32_t     origin_offset      = 0;  ///< BDL0 block offset inside the PKG
    uint32_t     origin_bdl_file_size      = 0;  ///< BDL0::fileSize
    uint32_t     origin_bdl_compressed_size= 0;  ///< BDL0::compressedSize (0 = uncompressed)
};

/* =========================================================================
 * PkgUnpacker
 * ========================================================================= */

/**
 * @brief Main unpacker class.
 *
 * Walks the BPK0 directory table, spawns async workers to decompress and
 * convert individual entries, then writes results sequentially to avoid
 * thundering-herd IO contention.
 */
class PkgUnpacker {
public:
    /**
     * @param base         Start of the memory-mapped PKG file.
     * @param mapped_size  Total size of the mapping in bytes.
     * @param out_root     Root directory for extracted files.
     */
    PkgUnpacker(const uint8_t* base, size_t mapped_size, fs::path out_root)
        : base_(base), mapped_size_(mapped_size), out_root_(std::move(out_root))
    {
        manifest_["directories"] = json::array();
    }

    /**
     * @brief Entry point: walk the directory table and extract all files.
     *
     * @param dir_table_offset  Byte offset of the first RawDirectory record.
     * @param dir_count         Number of directory entries to process.
     * @param manifest_path     Where to write the resulting manifest JSON.
     */
    void unpack(uint32_t dir_table_offset, uint32_t dir_count,
                const fs::path& manifest_path)
    {
        /* Validate that the directory table fits within the mapping */
        check_bounds(mapped_size_, dir_table_offset, 0, "directory table start");

        /* ----------------------------------------------------------------
         * Phase 1 — parse the directory table and launch async workers for
         * every file entry.  Workers perform CPU-bound work (decompress,
         * charset convert) concurrently; IO is deferred to Phase 2.
         * ---------------------------------------------------------------- */
        struct DirMeta {
            std::string utf8_name;
            uint32_t    origin_dir_unk0 = 0;
            /* futures for each file inside this directory */
            std::vector<std::future<FileRecord>> futures;
        };
        std::vector<DirMeta> dir_metas;
        dir_metas.reserve(dir_count);

        const uint8_t* ptr = base_ + dir_table_offset;

        for (uint32_t i = 0; i < dir_count; ++i) {
            /* Read RawDirectory header */
            check_bounds(mapped_size_,
                         static_cast<size_t>(ptr - base_), sizeof(RawDirectory),
                         "RawDirectory header");
            auto* raw_dir = reinterpret_cast<const RawDirectory*>(ptr);
            ptr += sizeof(RawDirectory);

            /* Read the CP932 directory name that follows the header */
            std::string raw_dir_name(reinterpret_cast<const char*>(ptr));
            std::string utf8_dir = cp932_to_utf8(raw_dir_name);
            /* Advance past name + alignment to 4-byte boundary */
            ptr += (raw_dir_name.size() + 1 + 3) & ~size_t(3);

            DirMeta dm;
            dm.utf8_name       = utf8_dir;
            dm.origin_dir_unk0 = raw_dir->unk0;

            /* Locate the file-entry array and the name-string block */
            const uint8_t* entry_ptr =
                base_ + raw_dir->offset;
            const char* name_ptr =
                reinterpret_cast<const char*>(
                    entry_ptr + sizeof(RawEntry) * raw_dir->num);

            /* Launch one async task per file */
            for (uint32_t j = 0; j < raw_dir->num; ++j) {
                check_bounds(mapped_size_,
                             static_cast<size_t>((entry_ptr + j * sizeof(RawEntry)) - base_),
                             sizeof(RawEntry), "RawEntry");

                auto* raw_entry =
                    reinterpret_cast<const RawEntry*>(entry_ptr + j * sizeof(RawEntry));

                std::string raw_file_name(name_ptr);
                std::string utf8_file = cp932_to_utf8(raw_file_name);
                name_ptr += raw_file_name.size() + 1;

                /* Capture everything needed by the worker by value */
                const uint8_t* base_cap      = base_;
                size_t         msize_cap     = mapped_size_;
                fs::path       out_root_cap  = out_root_;
                RawEntry       entry_copy    = *raw_entry;
                std::string    dir_utf8_copy = utf8_dir;
                std::string    file_utf8_copy= utf8_file;

                dm.futures.push_back(
                    std::async(std::launch::async,
                        [base_cap, msize_cap, out_root_cap,
                         entry_copy, dir_utf8_copy, file_utf8_copy]()
                        {
                            return process_file_entry(
                                base_cap, msize_cap, out_root_cap,
                                entry_copy, dir_utf8_copy, file_utf8_copy);
                        }));
            }

            dir_metas.push_back(std::move(dm));
        }

        /* ----------------------------------------------------------------
         * Phase 2 — collect results from workers, write files, build JSON.
         * Sequential IO avoids disk seek thrashing.
         * ---------------------------------------------------------------- */
        for (auto& dm : dir_metas) {
            json dir_json = {
                {"name",             dm.utf8_name},
                {"origin_dir_unk0",  dm.origin_dir_unk0},
                {"files",            json::array()}
            };

            for (auto& fut : dm.futures) {
                FileRecord rec = fut.get();   /* may rethrow worker exceptions */

                /* Create output directory tree if needed */
                fs::create_directories(rec.save_path.parent_path());

                /* Write extracted/converted content */
                std::ofstream ofs(rec.save_path, std::ios::binary);
                if (!ofs)
                    throw std::runtime_error("Cannot open for writing: " +
                                             rec.save_path.string());
                ofs.write(reinterpret_cast<const char*>(rec.payload.data()),
                          static_cast<std::streamsize>(rec.payload.size()));

                /* Append file metadata to the directory JSON node.
                 * NOTE: origin_bdl_file_size and origin_bdl_compressed_size
                 * are stored here so that the repacker can reconstruct the
                 * BDL0 header without reading the original PKG. */
                dir_json["files"].push_back({
                    {"name",                      rec.file_utf8},
                    {"origin_entry_unk0",          rec.origin_entry_unk0},
                    {"origin_entry_unk1",          rec.origin_entry_unk1},
                    {"origin_entry_size",          rec.origin_entry_size},
                    {"was_compressed",             rec.was_compressed},
                    {"origin_offset",              rec.origin_offset},
                    {"origin_bdl_file_size",       rec.origin_bdl_file_size},
                    {"origin_bdl_compressed_size", rec.origin_bdl_compressed_size},
                    {"is_text",                    rec.is_text}
                });
            }

            manifest_["directories"].push_back(std::move(dir_json));
        }

        /* ----------------------------------------------------------------
         * Phase 3 — write manifest JSON
         * ---------------------------------------------------------------- */
        fs::create_directories(manifest_path.parent_path());
        std::ofstream manifest_ofs(manifest_path);
        if (!manifest_ofs)
            throw std::runtime_error("Cannot write manifest: " + manifest_path.string());
        manifest_ofs << manifest_.dump(4);

        std::cout << "[+] Unpack complete. Manifest written to "
                  << manifest_path << '\n';
    }

private:
    /* -----------------------------------------------------------------------
     * Static worker — runs in its own thread.
     * Performs decompression + charset conversion; no shared mutable state.
     * ----------------------------------------------------------------------- */

    /**
     * @brief Process a single archive entry (decompress + charset-convert).
     *
     * This function is called from a std::async worker.  It is intentionally
     * static to make the absence of shared mutable state explicit.
     *
     * @param base        Memory-mapped PKG base pointer.
     * @param msize       Size of the mapping.
     * @param out_root    Extraction root directory.
     * @param entry       Copy of the RawEntry struct for this file.
     * @param dir_utf8    UTF-8 directory name.
     * @param file_utf8   UTF-8 file name.
     * @return            Populated FileRecord ready for disk IO.
     */
    static FileRecord process_file_entry(
        const uint8_t* base,
        size_t         msize,
        const fs::path& out_root,
        const RawEntry& entry,
        const std::string& dir_utf8,
        const std::string& file_utf8)
    {
        FileRecord rec;
        rec.dir_utf8         = dir_utf8;
        rec.file_utf8        = file_utf8;
        rec.save_path        = out_root / dir_utf8 / file_utf8;
        rec.origin_entry_unk0= entry.unk0;
        rec.origin_entry_unk1= entry.unk1;
        rec.origin_entry_size= entry.size;
        rec.origin_offset    = entry.offset;

        /* Validate BDL0 header access */
        check_bounds(msize, entry.offset, sizeof(BDL0Header), "BDL0Header");
        auto* bdl = reinterpret_cast<const BDL0Header*>(base + entry.offset);

        rec.was_compressed           = (bdl->compressedSize > 0);
        rec.origin_bdl_file_size     = bdl->fileSize;
        rec.origin_bdl_compressed_size = bdl->compressedSize;

        /* Determine whether this file contains text we should re-encode */
        std::string ext = fs::path(file_utf8).extension().string();
        std::transform(ext.begin(), ext.end(), ext.begin(),
                       [](unsigned char c){ return std::toupper(c); });
        rec.is_text = (ext == ".NUT" || ext == ".XML");

        /* ------------------------------------------------------------------
         * Decompress or copy raw payload
         * ------------------------------------------------------------------ */
        const uint8_t* payload_ptr = base + entry.offset + sizeof(BDL0Header);

        if (rec.was_compressed) {
            /* Validate compressed data access */
            check_bounds(msize,
                         entry.offset + sizeof(BDL0Header),
                         bdl->compressedSize, "compressed payload");

            rec.payload.resize(bdl->fileSize);
            uLongf dest_len = bdl->fileSize;
            int z = uncompress(rec.payload.data(), &dest_len,
                               payload_ptr, bdl->compressedSize);
            if (z != Z_OK)
                throw std::runtime_error("zlib uncompress failed for: " + file_utf8);
            rec.payload.resize(dest_len);   /* paranoia — usually a no-op */
        } else {
            /* Uncompressed: direct copy from the mapping */
            check_bounds(msize,
                         entry.offset + sizeof(BDL0Header),
                         bdl->fileSize, "uncompressed payload");
            rec.payload.assign(payload_ptr, payload_ptr + bdl->fileSize);
        }

        /* ------------------------------------------------------------------
         * Text files: convert from CP932 to UTF-8 and normalise line endings
         * ------------------------------------------------------------------ */
        if (rec.is_text && !rec.payload.empty()) {
            std::string raw_content(reinterpret_cast<const char*>(rec.payload.data()),
                                    rec.payload.size());
            bool had_crlf = (raw_content.find("\r\n") != std::string::npos);
            std::string utf8_content = cp932_to_utf8(raw_content);

            if (had_crlf)
                utf8_content = normalize_to_crlf(utf8_content);

            rec.payload.assign(
                reinterpret_cast<const uint8_t*>(utf8_content.data()),
                reinterpret_cast<const uint8_t*>(utf8_content.data() + utf8_content.size()));
        }

        return rec;
    }

    /* -----------------------------------------------------------------------
     * Member data
     * ----------------------------------------------------------------------- */
    const uint8_t* base_;        ///< Base address of the memory-mapped PKG
    size_t         mapped_size_; ///< Total size of the mapping in bytes
    fs::path       out_root_;    ///< Root output directory for extracted files
    json           manifest_;    ///< Accumulated manifest (written at the end)
};

/* =========================================================================
 * main
 * ========================================================================= */

/**
 * @brief Program entry point.
 *
 * Parses command-line arguments, opens the PKG via mmap, and drives the
 * unpacker.
 *
 * @param argc  Argument count (expected: 5).
 * @param argv  [0] program, [1] pkg_path, [2] dir_table_offset (hex),
 *              [3] dir_count, [4] output_root
 */
int main(int argc, char* argv[])
{
    /* Ensure boost::locale uses UTF-8 for all conversions */
    boost::locale::generator gen;
    std::locale::global(gen("en_US.UTF-8"));

    if (argc != 5) {
        std::cerr << "Usage: " << argv[0]
                  << " <pkg_file> <dir_table_offset_hex> <dir_count> <output_root>\n"
                  << "Example: " << argv[0]
                  << " data/raw/NEVA.PKG 0x12242C10 345 data/workspace/raw_unpacked\n";
        return 1;
    }

    try {
        const char* pkg_path   = argv[1];
        uint32_t    dir_offset = static_cast<uint32_t>(std::stoul(argv[2], nullptr, 16));
        uint32_t    dir_count  = static_cast<uint32_t>(std::stoul(argv[3], nullptr, 10));
        fs::path    out_root   = argv[4];

        /* Memory-map the input PKG file for zero-copy sequential reads */
        bip::file_mapping  m_file(pkg_path, bip::read_only);
        bip::mapped_region region(m_file, bip::read_only);

        /* Optionally advise the OS to prefetch the entire file */
        region.advise(bip::mapped_region::advice_sequential);

        PkgUnpacker unpacker(
            static_cast<const uint8_t*>(region.get_address()),
            region.get_size(),
            out_root);

        unpacker.unpack(dir_offset, dir_count,
                        "data/workspace/manifest.json");

    } catch (const std::exception& e) {
        std::cerr << "Fatal Error: " << e.what() << '\n';
        return 1;
    }

    return 0;
}