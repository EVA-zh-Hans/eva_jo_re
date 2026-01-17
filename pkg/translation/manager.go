package translation

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gorm.io/gorm"

	"github.com/xeonliu/eva_jo/pkg/parser"
	"github.com/xeonliu/eva_jo/pkg/types"
)

// Manager 翻译管理器
type Manager struct {
	db        *gorm.DB
	nutParser *parser.NUTParser
	xmlParser *parser.XMLParser
}

// NewManager 创建新的翻译管理器
func NewManager(db *gorm.DB) *Manager {
	return &Manager{
		db:        db,
		nutParser: parser.NewNUTParser(db),
		xmlParser: parser.NewXMLParser(db),
	}
}

// InitDatabase 初始化数据库表
func (m *Manager) InitDatabase() error {
	return m.db.AutoMigrate(
		&types.GamePackage{},
		&types.GameFile{},
		&types.TextEntry{},
		&types.Translation{},
		&types.TranslationProject{},
	)
}

// ProcessGameFiles 批量处理游戏文件
func (m *Manager) ProcessGameFiles(packageName, packageVersion, inputDir string) error {
	// 创建或获取游戏包记录
	var gamePackage types.GamePackage
	if err := m.db.Where("name = ? AND version = ?", packageName, packageVersion).First(&gamePackage).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			gamePackage = types.GamePackage{
				Name:    packageName,
				Version: packageVersion,
				Path:    inputDir,
			}
			if err := m.db.Create(&gamePackage).Error; err != nil {
				return fmt.Errorf("failed to create game package: %w", err)
			}
		} else {
			return fmt.Errorf("failed to query game package: %w", err)
		}
	}

	// 遍历目录处理文件
	return filepath.Walk(inputDir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return err
		}

		// 只处理 NUT 和 XML 文件
		ext := strings.ToUpper(filepath.Ext(path))
		if ext != ".NUT" && ext != ".XML" {
			return nil
		}

		fmt.Printf("Processing file: %s\n", path)

		content, err := os.ReadFile(path)
		if err != nil {
			return fmt.Errorf("failed to read file %s: %w", path, err)
		}

		// 计算相对路径
		relPath, err := filepath.Rel(inputDir, path)
		if err != nil {
			return fmt.Errorf("failed to get relative path: %w", err)
		}

		// 处理文件
		if ext == ".NUT" {
			return m.nutParser.ProcessFile(gamePackage.ID, relPath, content)
		} else if ext == ".XML" {
			return m.xmlParser.ProcessXMLFile(gamePackage.ID, relPath, content)
		}

		return nil
	})
}

// GetPendingTranslations 获取待翻译文本（按优先级排序）
func (m *Manager) GetPendingTranslations(limit int) ([]types.Translation, error) {
	var translations []types.Translation
	return translations, m.db.Where("status = ?", types.TranslationStatusPending).
		Order("usage_count DESC, priority DESC").
		Limit(limit).
		Find(&translations).Error
}

// UpdateTranslation 更新翻译
func (m *Manager) UpdateTranslation(id uint, translatedText, translator string) error {
	return m.db.Model(&types.Translation{}).
		Where("id = ?", id).
		Updates(map[string]interface{}{
			"translated_text": translatedText,
			"translator":      translator,
			"status":          types.TranslationStatusTranslated,
		}).Error
}

// GetTranslationStats 获取翻译统计信息
func (m *Manager) GetTranslationStats() (map[string]int64, error) {
	stats := make(map[string]int64)

	// 总文本数量
	var total int64
	if err := m.db.Model(&types.Translation{}).Count(&total).Error; err != nil {
		return nil, err
	}
	stats["total"] = total

	// 各状态数量
	statuses := []string{
		types.TranslationStatusPending,
		types.TranslationStatusTranslated,
		types.TranslationStatusReviewed,
		types.TranslationStatusApproved,
	}

	for _, status := range statuses {
		var count int64
		if err := m.db.Model(&types.Translation{}).
			Where("status = ?", status).
			Count(&count).Error; err != nil {
			return nil, err
		}
		stats[status] = count
	}

	return stats, nil
}

// ExportTranslationsCSV 导出翻译为 CSV 格式
func (m *Manager) ExportTranslationsCSV(filename string) error {
	var translations []types.Translation
	if err := m.db.Find(&translations).Error; err != nil {
		return fmt.Errorf("failed to query translations: %w", err)
	}

	file, err := os.Create(filename)
	if err != nil {
		return fmt.Errorf("failed to create CSV file: %w", err)
	}
	defer file.Close()

	writer := csv.NewWriter(file)
	defer writer.Flush()

	// 写入标题行
	if err := writer.Write([]string{
		"ID", "OriginalText", "TranslatedText", "Status", "Translator", "UsageCount", "Notes",
	}); err != nil {
		return fmt.Errorf("failed to write CSV header: %w", err)
	}

	// 写入数据行
	for _, t := range translations {
		record := []string{
			fmt.Sprintf("%d", t.ID),
			t.OriginalText,
			t.TranslatedText,
			t.Status,
			t.Translator,
			fmt.Sprintf("%d", t.UsageCount),
			t.Notes,
		}
		if err := writer.Write(record); err != nil {
			return fmt.Errorf("failed to write CSV record: %w", err)
		}
	}

	return nil
}

// ExportTranslationEntry 翻译条目导出格式
type ExportTranslationEntry struct {
	Key         string `json:"key"`
	Original    string `json:"original"`
	Translation string `json:"translation"`
	Context     string `json:"context,omitempty"`
}

// ExportTranslationsJSON 为每个文件（NUT/XML）导出翻译为 JSON 格式
func (m *Manager) ExportTranslationsJSON(outputDir string) error {
	// 获取所有 NUT 和 XML 文件
	var gameFiles []types.GameFile
	if err := m.db.Where("file_type IN ?", []string{types.FileTypeNUT, types.FileTypeXML}).Find(&gameFiles).Error; err != nil {
		return fmt.Errorf("failed to query game files: %w", err)
	}

	// 为每个文件生成单独的 JSON
	seenOriginals := make(map[string]bool) // 记录已导出的原文
	for _, gameFile := range gameFiles {
		// 获取该文件的所有文本条目及其翻译
		var entries []types.TextEntry
		if err := m.db.Preload("Translation").
			Where("file_id = ?", gameFile.ID).
			Order("line_number ASC, column_start ASC").
			Find(&entries).Error; err != nil {
			return fmt.Errorf("failed to query text entries for file %s: %w", gameFile.Path, err)
		}

		if len(entries) == 0 {
			continue // 跳过没有文本的文件
		}

		// 构建导出数据，同时去重
		exportData := make([]ExportTranslationEntry, 0)

		for _, entry := range entries {
			// 检查该原文是否已经导出过
			if seenOriginals[entry.OriginalText] {
				continue // 跳过重复的字符串
			}
			seenOriginals[entry.OriginalText] = true

			translation := ""
			if entry.Translation != nil {
				translation = entry.Translation.TranslatedText
			}

			exportData = append(exportData, ExportTranslationEntry{
				Key:         entry.OriginalText, // 使用原文作为键
				Original:    entry.OriginalText,
				Translation: translation,
				Context:     entry.Context,
			})
		}

		// 生成输出文件名（基于游戏文件路径）
		outputFileName := filepath.Join(outputDir, generateJSONFileName(gameFile.Path))

		// 确保输出目录存在
		if err := os.MkdirAll(filepath.Dir(outputFileName), 0755); err != nil {
			return fmt.Errorf("failed to create output directory: %w", err)
		}

		// 创建 JSON 文件
		file, err := os.Create(outputFileName)
		if err != nil {
			return fmt.Errorf("failed to create JSON file %s: %w", outputFileName, err)
		}

		encoder := json.NewEncoder(file)
		encoder.SetIndent("", "  ")
		if err := encoder.Encode(exportData); err != nil {
			file.Close()
			return fmt.Errorf("failed to encode JSON for file %s: %w", gameFile.Path, err)
		}
		file.Close()

		fmt.Printf("Exported: %s (%d entries)\n", outputFileName, len(exportData))
	}

	fmt.Printf("Total Strings: %d\n", len(seenOriginals))

	return nil
}

// generateJSONFileName 根据游戏文件路径生成 JSON 文件名
func generateJSONFileName(gamePath string) string {
	// 将文件路径转换为 JSON 文件名
	// 例如: "BTL_ISR/BTL_ISR_Q1.NUT" -> "BTL_ISR/BTL_ISR_Q1.json"
	ext := filepath.Ext(gamePath)
	return gamePath[:len(gamePath)-len(ext)] + ".json"
}

// ImportTranslationsCSV 从 CSV 文件导入翻译
func (m *Manager) ImportTranslationsCSV(filename string) error {
	file, err := os.Open(filename)
	if err != nil {
		return fmt.Errorf("failed to open CSV file: %w", err)
	}
	defer file.Close()

	reader := csv.NewReader(file)
	records, err := reader.ReadAll()
	if err != nil {
		return fmt.Errorf("failed to read CSV: %w", err)
	}

	if len(records) < 2 {
		return fmt.Errorf("CSV file must have at least header and one data row")
	}

	// 跳过标题行
	for i := 1; i < len(records); i++ {
		record := records[i]
		if len(record) < 4 {
			continue
		}

		// 查找现有翻译记录
		var translation types.Translation
		if err := m.db.Where("original_text = ?", record[1]).First(&translation).Error; err != nil {
			continue // 跳过不存在的记录
		}

		// 更新翻译
		updates := map[string]interface{}{
			"translated_text": record[2],
			"status":          record[3],
		}
		if len(record) > 4 {
			updates["translator"] = record[4]
		}
		if len(record) > 6 {
			updates["notes"] = record[6]
		}

		if err := m.db.Model(&translation).Updates(updates).Error; err != nil {
			return fmt.Errorf("failed to update translation %d: %w", translation.ID, err)
		}
	}

	return nil
}

// SearchTranslations 搜索翻译记录
func (m *Manager) SearchTranslations(keyword string, status string, limit int) ([]types.Translation, error) {
	query := m.db.Model(&types.Translation{})

	if keyword != "" {
		query = query.Where("original_text LIKE ? OR translated_text LIKE ?", "%"+keyword+"%", "%"+keyword+"%")
	}

	if status != "" {
		query = query.Where("status = ?", status)
	}

	var translations []types.Translation
	return translations, query.Order("usage_count DESC").Limit(limit).Find(&translations).Error
}

// GetFileContext 获取文件中特定文本的上下文
func (m *Manager) GetFileContext(translationID uint) ([]types.TextEntry, error) {
	var entries []types.TextEntry
	return entries, m.db.Preload("File").
		Where("translation_id = ?", translationID).
		Find(&entries).Error
}
