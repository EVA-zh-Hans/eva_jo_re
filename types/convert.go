package types

import "encoding/binary"

func RawToAbstractDirectory(rawDir RawDirectory, name string, files []File) Directory {
	return Directory{
		Unk0:  rawDir.Unk0,
		Unk1:  rawDir.Unk1,
		Name:  name,
		Files: files,
	}
}

func RawToAbstractFile(rawEntry RawEntry, name string, header [32]byte) File {
	if binary.LittleEndian.Uint64(header[12:20]) != 0 {
		panic("HeaderUnk1 is not zero")
	}
	return File{
		Unk0:             rawEntry.Unk0,
		Unk1:             rawEntry.Unk1,
		Size:             rawEntry.Size,
		Name:             name,
		HeaderFileSize:   binary.LittleEndian.Uint32(header[4:8]),
		HeaderCompressed: binary.LittleEndian.Uint32(header[8:12]),
		HeaderUnk1:       binary.LittleEndian.Uint32(header[12:16]),
		HeaderUnk2:       binary.LittleEndian.Uint32(header[16:20]),
		OriginalOffset:   rawEntry.Offset,
	}
}

func AbstractToRawDirectory(dir Directory, offset uint32, size uint32) RawDirectory {
	return RawDirectory{
		Unk0:   dir.Unk0,
		Unk1:   dir.Unk1,
		Num:    uint16(len(dir.Files)),
		Offset: offset,
		Size:   size,
		Zero:   0,
	}
}

func AbstractToRawFile(file File) RawEntry {
	return RawEntry{
		Unk0:   file.Unk0,
		Unk1:   file.Unk1,
		Size:   file.Size,
		Offset: file.OriginalOffset,
	}
}
