package main

import (
	"bytes"
	"compress/zlib"
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

const PKG_NAME = "NEVA.PKG"

// const PKG_NAME = "NEVA_REPACK.PKG"

const DIR_ENTRY_START = 0x12242C10

// const DIR_ENTRY_START = 0x24e077b0
const DIR_ENTRY_NUM = 345

func parse_dirs(file *os.File) ([]types.Directory, error) {
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

func main() {
	f, err := os.Open(PKG_NAME)
	if err != nil {
		fmt.Println("Error opening file:", err)
		return
	}

	defer f.Close()

	directories, err := parse_dirs(f)
	if err != nil {
		fmt.Println("Error parsing directories:", err)
		return
	}

	for _, directory := range directories {
		fmt.Printf("Directory: %+v\n", directory)
	}

	// Dump all the files

	for _, directory := range directories {
		// Create directory
		err := os.MkdirAll(directory.Name, os.ModePerm)
		if err != nil {
			fmt.Println("Error creating directory:", err)
			return
		}

		for _, file := range directory.Files {
			fmt.Printf("File: %+v\n", file)

			// Seek to the file
			_, err := f.Seek(int64(file.OriginalOffset+32), io.SeekStart)
			if err != nil {
				fmt.Println("Error seeking to file:", err)
				return
			}

			// Read the file
			data := make([]byte, file.Size)

			// Decompress if needed
			if file.HeaderCompressed != 0 {
				data = make([]byte, file.HeaderCompressed)
				_, err = f.Read(data)
				// Decompress
				fmt.Println("Decompressing file:", file.Name)
				// Decompress
				fmt.Println("Decompressing file:", file.Name)
				b := bytes.NewReader(data)
				r, err := zlib.NewReader(b)
				if err != nil {
					fmt.Println("Error decompressing file content:", err)
					return
				}
				var decompressedContent bytes.Buffer
				_, err = io.Copy(&decompressedContent, r)
				if err != nil {
					fmt.Println("Error decompressing file content:", err)
					return
				}
				data = decompressedContent.Bytes()
			} else {
				_, err = f.Read(data)
			}

			// Write the file content to a new file in the corresponding directory
			filePath := filepath.Join(directory.Name, file.Name)
			err = os.WriteFile(filePath, data, 0644)
			if err != nil {
				fmt.Println("Error writing file:", err)
				return
			}
		}
	}

	// Dump to yaml file
	data, err := yaml.Marshal(directories)

	yamlFile, err := os.Create("NEVA.yaml")
	if err != nil {
		fmt.Println("Error creating yaml file:", err)
		return
	}

	defer yamlFile.Close()

	_, err = yamlFile.Write(data)
	if err != nil {
		fmt.Println("Error writing yaml file:", err)
		return
	}
}
