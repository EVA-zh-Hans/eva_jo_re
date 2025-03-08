package main

import (
	"bytes"
	"compress/zlib"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/xeonliu/eva_jo/pkg/unpack"
	"gopkg.in/yaml.v3"
)

func main() {

	pkgName := flag.String("pkg", "NEVA.PKG", "The name of the package file")
	outputDir := flag.String("output", "", "The output directory")

	flag.Parse()

	if *outputDir == "" {
		fmt.Println("Output directory is required")
		flag.Usage()
		os.Exit(1)
	}

	f, err := os.Open(*pkgName)
	if err != nil {
		fmt.Println("Error opening file:", err)
		return
	}

	defer f.Close()

	directories, err := unpack.ParseDirs(f)
	if err != nil {
		fmt.Println("Error parsing directories:", err)
		return
	}

	for _, directory := range directories {
		fmt.Printf("Directory: %+v\n", directory)
	}

	// Dump all the files

	for _, directory := range directories {

		// Concat the output directory
		var dir_name = filepath.Join(*outputDir, directory.Name)
		// Create directory
		err := os.MkdirAll(dir_name, os.ModePerm)
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

			// NOTE: Only Decompress NUT
			// Decompress if needed
			if file.HeaderCompressed != 0 && strings.HasSuffix(file.Name, ".NUT") {
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
			filePath := filepath.Join(dir_name, file.Name)
			err = os.WriteFile(filePath, data, 0644)
			if err != nil {
				fmt.Println("Error writing file:", err)
				return
			}
		}
	}

	// Dump to yaml file
	data, err := yaml.Marshal(directories)
	if err != nil {
		fmt.Println("Error marshalling yaml:", err)
		return
	}

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
