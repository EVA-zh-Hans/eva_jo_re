#pragma once
#include <cstdint>

#pragma pack(push, 1)
struct RawDirectory {
    uint32_t unk0;
    uint16_t unk1;
    uint16_t num;
    uint32_t offset;
    uint32_t size;
    uint32_t zero;
};

struct RawEntry {
    uint32_t unk0;           // Offset to file entry name
    // 实测规则：按“封包内存储体大小 + BDL0Header(0x20)”再向上 0x800 对齐。
    // stored_size = (BDL0.compressedSize > 0 ? BDL0.compressedSize : BDL0.fileSize)
    // unk1 = align(stored_size + 0x20, 0x800)
    uint32_t unk1;
    // 实测规则：等于 BDL0.fileSize（解压后原始大小），不是压缩后大小，也不包含 0x20 头。
    uint32_t size;
    uint32_t offset;
};

struct BDL0Header {
    char magic[4];           // "BDL0"
    uint32_t fileSize;       // 解压后的原始大小
    uint32_t compressedSize; // 压缩后的大小（若为0则未压缩）
    // 原包实测通常为 0
    uint32_t unk1;
    // 原包实测通常为 0
    uint32_t unk2;
    uint8_t padding[12];
};

struct BPK0Header {
    char     magic[4] = {'B', 'P', 'K', '0'};
    uint32_t unk_const = 0x000025AC; 
    uint32_t dir_offset;        // 目录表起始位置
    uint32_t dir_entry_diff;    // dir_offset - entry_offset
    uint32_t entry_offset;      // 首个文件 Entry 的起始位置
};
#pragma pack(pop)