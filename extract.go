// package main

// import (
// 	"bytes"
// 	"encoding/binary"
// 	"fmt"
// 	"io"
// 	"os"

// 	"github.com/xeonliu/eva_jo/types"
// 	"golang.org/x/text/encoding/japanese"
// 	"golang.org/x/text/transform"
// )

// type Directory types.RawDirectory
// type Entry types.RawEntry

// const PKG_NAME = "NEVA.PKG"
// const DIR_ENTRY_START = 0x12242C10
// const DIR_ENTRY_NUM = 345

// func parse_dirs(file *os.File) ([]types.Directory, error) {
// 	// Seek to the Directory structure at 0x12242C10
// 	_, err := file.Seek(DIR_ENTRY_START, io.SeekStart)
// 	if err != nil {
// 		return nil, err
// 	}

// 	// Read the Directory structures
// 	var directories []types.Directory
// 	for i := 0; i < DIR_ENTRY_NUM; i++ {
// 		var directory types.RawDirectory
// 		err = binary.Read(file, binary.LittleEndian, &directory)
// 		if err != nil {
// 			return nil, err
// 		}

// 		// Read the MyString structure (variable length)
// 		var nameBuf bytes.Buffer
// 		for {
// 			var char byte
// 			err = binary.Read(file, binary.LittleEndian, &char)
// 			if err != nil {
// 				return nil, err
// 			}
// 			if char == 0 {
// 				break
// 			}
// 			nameBuf.WriteByte(char)
// 		}

// 		// 4-byte alignment
// 		currentOffset, err := file.Seek(0, io.SeekCurrent)
// 		if err != nil {
// 			return nil, err
// 		}
// 		padding := (4 - (currentOffset % 4)) % 4
// 		_, err = file.Seek(padding, io.SeekCurrent)
// 		if err != nil {
// 			return nil, err
// 		}

// 		// convert to string using CP932 encoding
// 		decoded_name, _, err := transform.String(japanese.ShiftJIS.NewDecoder(), nameBuf.String())
// 		if err != nil {
// 			return nil, err
// 		}

// 		var parsed_dir types.Directory
// 		parsed_dir.Unk0 = directory.Unk0
// 		parsed_dir.Unk1 = directory.Unk1
// 		parsed_dir.Name = decoded_name

// 		if directory.Zero != 0 {
// 			fmt.Printf("Zero: %d\n", directory.Zero)
// 			panic("Zero is not zero")
// 		}

// 		fmt.Printf("Directory: %+v, Name: %s\n", directory, decoded_name)

// 		directories = append(directories, parsed_dir)
// 	}

// 	return directories, nil
// }

// func parse_files(file *os.File, directory Directory) ([]Entry, []string, error) {
// 	// Seek to the Entry structures
// 	_, err := file.Seek(int64(directory.Offset), io.SeekStart)
// 	if err != nil {
// 		return nil, nil, err
// 	}

// 	// Read the Entry structures
// 	var entries []Entry
// 	for j := 0; j < int(directory.Num); j++ {
// 		var entry Entry
// 		err = binary.Read(file, binary.LittleEndian, &entry)
// 		if err != nil {
// 			return nil, nil, err
// 		}
// 		entries = append(entries, entry)
// 	}

// 	// Read the null-terminated strings for each Entry
// 	var entryNames []string
// 	for j := 0; j < int(directory.Num); j++ {
// 		var nameBuf bytes.Buffer
// 		for {
// 			var char byte
// 			err = binary.Read(file, binary.LittleEndian, &char)
// 			if err != nil {
// 				return nil, nil, err
// 			}
// 			if char == 0 {
// 				break
// 			}
// 			nameBuf.WriteByte(char)
// 		}
// 		entryNames = append(entryNames, nameBuf.String())
// 	}

// 	return entries, entryNames, nil
// }

// func main() {
// 	file, err := os.Open(PKG_NAME)
// 	if err != nil {
// 		fmt.Println("Error opening file:", err)
// 		return
// 	}
// 	defer file.Close()

// 	directories, err := parse_dirs(file)

// 	for _, directory := range directories {
// 		// Print the parsed data
// 		fmt.Printf("Directory: %+v\n", directory)
// 	}

// 	// // Seek to the Directory structure at 0x12242C10
// 	// _, err = file.Seek(DIR_ENTRY_START, io.SeekStart)
// 	// if err != nil {
// 	// 	fmt.Println("Error seeking file:", err)
// 	// 	return
// 	// }

// 	// // Read the Directory structures
// 	// var directories []Directory
// 	// for i := 0; i < DIR_ENTRY_NUM; i++ {
// 	// 	var directory Directory
// 	// 	err = binary.Read(file, binary.LittleEndian, &directory)
// 	// 	if err != nil {
// 	// 		fmt.Println("Error reading directory:", err)
// 	// 		return
// 	// 	}

// 	// 	// Read the MyString structure (variable length)
// 	// 	var nameBuf bytes.Buffer
// 	// 	for {
// 	// 		var char byte
// 	// 		err = binary.Read(file, binary.LittleEndian, &char)
// 	// 		if err != nil {
// 	// 			fmt.Println("Error reading name:", err)
// 	// 			return
// 	// 		}
// 	// 		if char == 0 {
// 	// 			break
// 	// 		}
// 	// 		nameBuf.WriteByte(char)
// 	// 	}
// 	// 	name := nameBuf.String()

// 	// 	// 4-byte alignment
// 	// 	_, err = file.Seek((4 - int64(io.SeekCurrent)%4), io.SeekCurrent)
// 	// 	if err != nil {
// 	// 		fmt.Println("Error seeking file:", err)
// 	// 		return
// 	// 	}

// 	// 	directories = append(directories, directory)
// 	// 	fmt.Println("Deal with directory:", name)
// 	// 	fmt.Printf("  unk0: %d, unk1: %d, num: %d, offset: %d, size: %d, zero: %d\n", directory.Unk0, directory.Unk1, directory.Num, directory.Offset, directory.Size, directory.Zero)

// 	// 	// Create directory if it doesn't exist
// 	// 	if _, err := os.Stat(name); os.IsNotExist(err) {
// 	// 		err = os.Mkdir(name, 0755)
// 	// 		if err != nil {
// 	// 			fmt.Println("Error creating directory:", err)
// 	// 			return
// 	// 		}
// 	// 	}

// 	// 	// Seek to the Entry structures
// 	// 	_, err = file.Seek(int64(directory.Offset), io.SeekStart)
// 	// 	if err != nil {
// 	// 		fmt.Println("Error seeking file:", err)
// 	// 		return
// 	// 	}

// 	// 	// Read the Entry structures
// 	// 	var entries []Entry
// 	// 	for j := 0; j < int(directory.Num); j++ {
// 	// 		var entry Entry
// 	// 		err = binary.Read(file, binary.LittleEndian, &entry)
// 	// 		if err != nil {
// 	// 			fmt.Println("Error reading entry:", err)
// 	// 			return
// 	// 		}
// 	// 		entries = append(entries, entry)
// 	// 	}

// 	// 	// Read the null-terminated strings for each Entry
// 	// 	var entryNames []string
// 	// 	for j := 0; j < int(directory.Num); j++ {
// 	// 		var nameBuf bytes.Buffer
// 	// 		for {
// 	// 			var char byte
// 	// 			err = binary.Read(file, binary.LittleEndian, &char)
// 	// 			if err != nil {
// 	// 				fmt.Println("Error reading entry name:", err)
// 	// 				return
// 	// 			}
// 	// 			if char == 0 {
// 	// 				break
// 	// 			}
// 	// 			nameBuf.WriteByte(char)
// 	// 		}
// 	// 		entryNames = append(entryNames, nameBuf.String())
// 	// 	}

// 	// 	// Print the parsed data
// 	// 	fmt.Printf("Directory: %+v, Name: %s\n", directory, name)
// 	// 	for k, entry := range entries {
// 	// 		fmt.Printf("  Entry: %+v, Name: %s\n", entry, entryNames[k])

// 	// 		// Extract the file content
// 	// 		fileOffset := entry.Offset
// 	// 		fileSize := entry.Size

// 	// 		// Seek to the file content
// 	// 		_, err = file.Seek(int64(fileOffset), io.SeekStart)
// 	// 		if err != nil {
// 	// 			fmt.Println("Error seeking file:", err)
// 	// 			return
// 	// 		}

// 	// 		// Read the file header
// 	// 		fileHeader := make([]byte, 32)
// 	// 		_, err = file.Read(fileHeader)
// 	// 		if err != nil {
// 	// 			fmt.Println("Error reading file header:", err)
// 	// 			return
// 	// 		}

// 	// 		// Check if the file is compressed
// 	// 		isCompressed := binary.LittleEndian.Uint32(fileHeader[8:12]) != 0

// 	// 		// Read the file content
// 	// 		fileContent := make([]byte, fileSize)
// 	// 		_, err = file.Read(fileContent)
// 	// 		if err != nil {
// 	// 			fmt.Println("Error reading file content:", err)
// 	// 			return
// 	// 		}

// 	// 		if isCompressed {
// 	// 			// Decompress the file content
// 	// 			b := bytes.NewReader(fileContent)
// 	// 			r, err := zlib.NewReader(b)
// 	// 			if err != nil {
// 	// 				fmt.Println("Error decompressing file content:", err)
// 	// 				return
// 	// 			}
// 	// 			var decompressedContent bytes.Buffer
// 	// 			_, err = io.Copy(&decompressedContent, r)
// 	// 			if err != nil {
// 	// 				fmt.Println("Error decompressing file content:", err)
// 	// 				return
// 	// 			}
// 	// 			fileContent = decompressedContent.Bytes()
// 	// 		}

// 	// 		// Write the file content to a new file in the corresponding directory
// 	// 		filePath := filepath.Join(name, entryNames[k])
// 	// 		err = os.WriteFile(filePath, fileContent, 0644)
// 	// 		if err != nil {
// 	// 			fmt.Println("Error writing file:", err)
// 	// 			return
// 	// 		}
// 	// 	}
// 	// }
// }
