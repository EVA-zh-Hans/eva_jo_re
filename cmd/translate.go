package main

import (
	"flag"
	"fmt"
	"log"
	"os"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"

	"github.com/xeonliu/eva_jo/pkg/translation"
)

func main() {
	var (
		dbPath       = flag.String("db", "translation.db", "SQLite database path")
		inputDir     = flag.String("input", "", "Input directory containing game files")
		packageName  = flag.String("package", "EVA_JO", "Game package name")
		version      = flag.String("version", "1.0", "Package version")
		action       = flag.String("action", "process", "Action: process, export, import, stats, search")
		exportFile   = flag.String("export", "", "Export file path or directory")
		exportFormat = flag.String("format", "csv", "Export format: csv or json")
		importFile   = flag.String("import", "", "Import file path (CSV)")
		keyword      = flag.String("keyword", "", "Search keyword")
		status       = flag.String("status", "", "Filter by status")
		limit        = flag.Int("limit", 100, "Limit number of results")
	)
	flag.Parse()

	// 连接数据库
	db, err := gorm.Open(sqlite.Open(*dbPath), &gorm.Config{})
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}

	// 创建翻译管理器
	manager := translation.NewManager(db)

	// 初始化数据库
	if err := manager.InitDatabase(); err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}

	switch *action {
	case "process":
		if *inputDir == "" {
			log.Fatal("Input directory is required for process action")
		}
		fmt.Printf("Processing files in %s...\n", *inputDir)
		if err := manager.ProcessGameFiles(*packageName, *version, *inputDir); err != nil {
			log.Fatalf("Failed to process files: %v", err)
		}
		fmt.Println("Processing completed!")

	case "stats":
		stats, err := manager.GetTranslationStats()
		if err != nil {
			log.Fatalf("Failed to get stats: %v", err)
		}
		fmt.Println("Translation Statistics:")
		for key, value := range stats {
			fmt.Printf("  %s: %d\n", key, value)
		}

	case "export":
		if *exportFile == "" {
			log.Fatal("Export file path or directory is required")
		}
		fmt.Printf("Exporting translations to %s (format: %s)...\n", *exportFile, *exportFormat)

		if *exportFormat == "json" {
			// JSON 导出到目录
			err = manager.ExportTranslationsJSON(*exportFile)
		} else {
			// CSV 导出到文件
			err = manager.ExportTranslationsCSV(*exportFile)
		}

		if err != nil {
			log.Fatalf("Failed to export: %v", err)
		}
		fmt.Println("Export completed!")

	case "import":
		if *importFile == "" {
			log.Fatal("Import file path is required")
		}
		fmt.Printf("Importing translations from %s...\n", *importFile)
		if err := manager.ImportTranslationsCSV(*importFile); err != nil {
			log.Fatalf("Failed to import: %v", err)
		}
		fmt.Println("Import completed!")

	case "search":
		translations, err := manager.SearchTranslations(*keyword, *status, *limit)
		if err != nil {
			log.Fatalf("Failed to search: %v", err)
		}

		fmt.Printf("Found %d translations:\n", len(translations))
		for _, t := range translations {
			fmt.Printf("ID: %d, Status: %s, Usage: %d\n", t.ID, t.Status, t.UsageCount)
			fmt.Printf("Original: %s\n", t.OriginalText)
			if t.TranslatedText != "" {
				fmt.Printf("Translated: %s\n", t.TranslatedText)
			}
			fmt.Println("---")
		}

	case "pending":
		translations, err := manager.GetPendingTranslations(*limit)
		if err != nil {
			log.Fatalf("Failed to get pending translations: %v", err)
		}

		fmt.Printf("Top %d pending translations (by usage count):\n", len(translations))
		for i, t := range translations {
			fmt.Printf("%d. [ID: %d] Usage: %d\n", i+1, t.ID, t.UsageCount)
			fmt.Printf("   Text: %s\n", t.OriginalText)
		}

	default:
		fmt.Printf("Unknown action: %s\n", *action)
		fmt.Println("Available actions: process, export, import, stats, search, pending")
		os.Exit(1)
	}
}
