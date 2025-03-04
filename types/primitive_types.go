package types

type RawDirectory struct {
	Unk0 uint32
	Unk1 uint16
	Num  uint16

	Offset uint32 // 0x10对齐
	Size   uint32
	Zero   uint32
}

type RawEntry struct {
	Unk0   uint32
	Unk1   uint32
	Size   uint32
	Offset uint32 // 0x800 对齐
}
