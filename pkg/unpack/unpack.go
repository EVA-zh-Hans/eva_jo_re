package unpack

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"io"
	"os"

	"github.com/xeonliu/eva_jo/pkg/types"
	"golang.org/x/text/encoding/japanese"
	"golang.org/x/text/transform"
)

const PKG_NAME = "NEVA.PKG"

const DIR_ENTRY_START = 0x12242C10

const DIR_ENTRY_NUM = 345

// 首字母大写代表导出
func ParseDirs(file *os.File) ([]types.Directory, error) {
	_, err := file.Seek(DIR_ENTRY_START, io.SeekStart)
	if err != nil {
		return nil, err
	}

	var directories []types.Directory
	for i := 0; i < DIR_ENTRY_NUM; i++ {
		var rawDir types.RawDirectory
		err = binary.Read(file, binary.LittleEndian, &rawDir)
		if err != nil {
			return nil, err
		}

		var nameBuf bytes.Buffer
		for {
			var char byte
			err = binary.Read(file, binary.LittleEndian, &char)
			if err != nil {
				return nil, err
			}
			if char == 0 {
				break
			}
			nameBuf.WriteByte(char)
		}

		currentOffset, err := file.Seek(0, io.SeekCurrent)
		if err != nil {
			return nil, err
		}
		padding := (4 - (currentOffset % 4)) % 4
		_, err = file.Seek(padding, io.SeekCurrent)
		if err != nil {
			return nil, err
		}

		decoded_name, _, err := transform.String(japanese.ShiftJIS.NewDecoder(), nameBuf.String())
		if err != nil {
			return nil, err
		}

		fmt.Println("Decoded name:", decoded_name)

		// 备份文件指针
		offset, err := file.Seek(0, io.SeekCurrent)

		files, err := parse_files(file, rawDir)
		if err != nil {
			return nil, err
		}

		// 恢复文件指针
		_, err = file.Seek(offset, io.SeekStart)

		parsed_dir := types.RawToAbstractDirectory(rawDir, decoded_name, files)
		directories = append(directories, parsed_dir)
	}

	return directories, nil
}

func parse_files(file *os.File, rawDir types.RawDirectory) ([]types.File, error) {
	_, err := file.Seek(int64(rawDir.Offset), io.SeekStart)
	if err != nil {
		return nil, err
	}

	var rawEntries []types.RawEntry
	for j := 0; j < int(rawDir.Num); j++ {
		var rawEntry types.RawEntry
		err = binary.Read(file, binary.LittleEndian, &rawEntry)
		if err != nil {
			return nil, err
		}
		rawEntries = append(rawEntries, rawEntry)
	}

	var fileNames []string
	for j := 0; j < int(rawDir.Num); j++ {
		var nameBuf bytes.Buffer
		for {
			var char byte
			err = binary.Read(file, binary.LittleEndian, &char)
			if err != nil {
				return nil, err
			}
			if char == 0 {
				break
			}
			nameBuf.WriteByte(char)
		}

		decoded_name, _, err := transform.String(japanese.ShiftJIS.NewDecoder(), nameBuf.String())
		if err != nil {
			return nil, err
		}
		fileNames = append(fileNames, decoded_name)
	}

	// Backup file pointer
	offset, err := file.Seek(0, io.SeekCurrent)

	var files []types.File
	for j := 0; j < int(rawDir.Num); j++ {
		_, err = file.Seek(int64(rawEntries[j].Offset), io.SeekStart)
		var header [32]byte
		_, err = file.Read(header[:])
		if err != nil {
			return nil, err
		}
		parsed_file := types.RawToAbstractFile(rawEntries[j], fileNames[j], header)
		files = append(files, parsed_file)
	}

	// Restore file pointer
	_, err = file.Seek(offset, io.SeekStart)

	return files, nil
}
