package main

import (
	"flag"

	"github.com/xeonliu/eva_jo/pkg/repack"
)

func main() {
	metadataFile := flag.String("metadata", "NEVA.yaml", "The metadata file")
	inputDir := flag.String("input", "output", "The output directory")
	pkgName := flag.String("pkg", "NEVA_RE.PKG", "The name of the package file")

	flag.Parse()

	if *metadataFile == "" || *inputDir == "" {
		flag.Usage()
		return
	}

	repack.Repack(*metadataFile, *pkgName, *inputDir)
}
