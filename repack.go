package main

import (
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/xeonliu/eva_jo/types"
	"golang.org/x/text/encoding/japanese"
	"golang.org/x/text/transform"
	"gopkg.in/yaml.v3"
)

const PKG_NAME = "NEVA_REPACK.PKG"

func readYAML(filename string) ([]types.Directory, error) {
	data, err := os.ReadFile(filename)
	if err != nil {
		return nil, err
	}

	var directories []types.Directory
	err = yaml.Unmarshal(data, &directories)
	if err != nil {
		return nil, err
	}

	return directories, nil
}

func main() {
	directories, err := readYAML("NEVA.yaml")
	if err != nil {
		fmt.Println("Error reading YAML file:", err)
		return
	}

	f, err := os.Create(PKG_NAME)
	if err != nil {
		fmt.Println("Error creating file:", err)
		return
	}
	defer f.Close()

	// 首先写入文件头
	// BPK0
	// 30 AC 25 00
	// 目录的Offset 0x12242C10
	// 10 34 05 00
	// 首个Entry的Offset 0x121EF800

	var dir_offset uint32 = 0x12242C10
	var entry_offset uint32 = 0x121EF800

	f.WriteString("BPK0")
	f.Write([]byte{0x30, 0xAC, 0x25, 0x00})
	binary.Write(f, binary.LittleEndian, uint32(dir_offset))
	f.Write([]byte{0x10, 0x34, 0x05, 0x00})
	binary.Write(f, binary.LittleEndian, uint32(entry_offset))

	// 找到目录对应的文件
	// 在0x800对齐的位置写入文件头和文件
	// 记住所有文件的偏移量和大小
	for dirIndex, directory := range directories {
		fmt.Println("Repacking directory:", directory.Name)
		for fileIndex, file := range directory.Files {
			fmt.Println("Repacking file:", file.Name)
			currentOffset, _ := f.Seek(0, io.SeekCurrent)
			padding := (0x800 - (currentOffset % 0x800)) % 0x800
			f.Seek(padding, io.SeekCurrent)

			currentOffset, _ = f.Seek(0, io.SeekCurrent)

			fmt.Println("Current offset:", currentOffset)

			// 从对应的目录打开对应的文件
			fileContent, err := os.ReadFile(filepath.Join(directory.Name, file.Name))
			if err != nil {
				fmt.Println("Error reading file:", err)
				return
			}

			// 记住文件偏移量
			file.OriginalOffset = uint32(currentOffset)

			// 记住文件大小
			file.Size = uint32(len(fileContent))
			file.HeaderFileSize = file.Size

			// BufferSize向上取整到2048
			file.BufferSize = (file.Size + 0x7FF) & ^uint32(0x7FF)

			// 压缩标志位
			file.HeaderCompressed = 0

			// // TODO: 进行DEFLATE压缩
			// if file.HeaderCompressed != 0 {
			// 	fmt.Println("Compressing file:", file.Name)
			// 	// Compress
			// 	var compressedContent bytes.Buffer
			// 	writer := zlib.NewWriter(&compressedContent)
			// 	_, err := writer.Write(fileContent)
			// 	if err != nil {
			// 		fmt.Println("Error compressing file:", err)
			// 		return
			// 	}
			// 	writer.Close()

			// 	// 压缩后大小
			// 	file.HeaderCompressed = uint32(len(fileContent))
			// }

			// 妈的，还得手动修改
			directories[dirIndex].Files[fileIndex] = file

			// 写入文件头
			f.WriteString("BDL0")
			binary.Write(f, binary.LittleEndian, uint32(file.HeaderFileSize))   // 4-7
			binary.Write(f, binary.LittleEndian, uint32(file.HeaderCompressed)) // 8-11
			binary.Write(f, binary.LittleEndian, uint32(file.HeaderUnk1))       // 12-15
			binary.Write(f, binary.LittleEndian, uint32(file.HeaderUnk2))       // 16-19
			f.Write(make([]byte, 12))                                           // 20-31

			// 写入文件内容
			_, err = f.Write(fileContent)
			if err != nil {
				fmt.Println("Error writing file content:", err)
				return
			}

		}
	}

	// 对齐到16字节
	currentOffset, _ := f.Seek(0, io.SeekCurrent)
	padding := (0x10 - (currentOffset % 0x10)) % 0x10
	f.Seek(padding, io.SeekCurrent)

	// 创建一个数组记录所有Entry的偏移量
	entryOffsets := make([]uint32, 0)
	// 写入所有Entry，记住偏移量，对齐到16字节
	for _, directory := range directories {
		// 更新目录的Entry偏移量
		currentOffset, _ := f.Seek(0, io.SeekCurrent)
		// TODO: Zero Offsets
		entryOffsets = append(entryOffsets, uint32(currentOffset))
		for _, file := range directory.Files {
			rawEntry := types.AbstractToRawFile(file)
			fmt.Printf("Writing entry: %+v\n", rawEntry)
			err := binary.Write(f, binary.LittleEndian, &rawEntry)
			if err != nil {
				fmt.Println("Error writing entry:", err)
				return
			}
		}

		// 写入文件名，\0结尾，以SJIS编码
		for _, file := range directory.Files {
			var filename = file.Name
			encoder := japanese.ShiftJIS.NewEncoder()
			encodedName, _, err := transform.String(encoder, filename)
			if err != nil {
				fmt.Println("Error encoding filename:", err)
				return
			}
			encodedName += "\x00"
			_, err = f.WriteString(encodedName)
		}

		// Align to 16 bytes
		currentOffset, err := f.Seek(0, io.SeekCurrent)
		if err != nil {
			fmt.Println("Error seeking file:", err)
			return
		}
		padding := (16 - (currentOffset % 16)) % 16
		f.Seek(padding, io.SeekCurrent)
	}

	// 写入目录的Entry
	for i, directory := range directories {
		if i == 0 {
			var currentOffset, _ = f.Seek(0, io.SeekCurrent)
			// 保存目录的偏移量
			dir_offset = uint32(currentOffset)
		}
		// TODO: Entry Size
		entrySize := uint32(0)
		if i < len(entryOffsets)-1 {
			entrySize = entryOffsets[i+1] - entryOffsets[i]
		}
		rawDir := types.AbstractToRawDirectory(directory, entryOffsets[i], entrySize)
		err := binary.Write(f, binary.LittleEndian, &rawDir)
		if err != nil {
			fmt.Println("Error writing directory entry:", err)
			return
		}
		// 写入目录名，\0结尾，以SJIS编码
		var dirname = directory.Name
		encoder := japanese.ShiftJIS.NewEncoder()
		encodedName, _, err := transform.String(encoder, dirname)
		if err != nil {
			fmt.Println("Error encoding directory name:", err)
			return
		}
		encodedName += "\x00"
		_, err = f.WriteString(encodedName)
		if err != nil {
			fmt.Println("Error writing directory name:", err)
			return
		}

		// Align to 4 bytes
		currentOffset, err := f.Seek(0, io.SeekCurrent)
		if err != nil {
			fmt.Println("Error seeking file:", err)
			return
		}
		padding := (4 - (currentOffset % 4)) % 4
		f.Seek(padding, io.SeekCurrent)
	}

	// 写入文件头
	f.Seek(8, io.SeekStart)
	binary.Write(f, binary.LittleEndian, uint32(dir_offset))
	f.Seek(16, io.SeekStart)
	entry_offset = entryOffsets[0]
	binary.Write(f, binary.LittleEndian, uint32(entry_offset))
	f.Seek(12, io.SeekStart)
	binary.Write(f, binary.LittleEndian, uint32(dir_offset-entry_offset))

	fmt.Println("Repack completed successfully.")
}
