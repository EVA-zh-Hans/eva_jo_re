package types

type Directory struct {
	Unk0  uint32
	Unk1  uint16
	Name  string
	Files []File
}

type File struct {
	Unk0 uint32
	Unk1 uint32
	Size uint32
	Name string
	// 32-byte header
	HeaderFileSize   uint32
	HeaderCompressed uint32
	// HeaderUnk1 is always 0
	HeaderUnk1 uint32
	// HeaderUnk2 is always 0
	HeaderUnk2 uint32

	OriginalOffset uint32 // 保留原始偏移量
}
