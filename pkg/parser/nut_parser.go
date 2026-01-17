package parser

import (
	"crypto/sha256"
	"fmt"
	"regexp"
	"strings"

	"golang.org/x/text/encoding/japanese"
	"golang.org/x/text/transform"
	"gorm.io/gorm"

	"github.com/xeonliu/eva_jo/pkg/types"
)

// NUTParser NUT 文件解析器
type NUTParser struct {
	db *gorm.DB
}

// NewNUTParser 创建新的 NUT 解析器
func NewNUTParser(db *gorm.DB) *NUTParser {
	return &NUTParser{db: db}
}

// ParsedText 解析结果
type ParsedText struct {
	Text        string
	LineNumber  int
	ColumnStart int
	ColumnEnd   int
	Type        string // "comment", "string_literal", "function_call"
	Context     string // 上下文
}

// ParseFile 解析 NUT 文件内容，提取日文字符串
func (p *NUTParser) ParseFile(filePath string, content []byte) ([]ParsedText, error) {
	// 1. SJIS -> UTF-8 转换
	decoder := japanese.ShiftJIS.NewDecoder()
	utf8Content, _, err := transform.Bytes(decoder, content)
	if err != nil {
		return nil, fmt.Errorf("failed to decode SJIS content: %w", err)
	}

	lines := strings.Split(string(utf8Content), "\n")
	var results []ParsedText

	for i, line := range lines {
		// 2. 提取日文字符串
		texts := p.extractJapaneseText(line, i+1)

		// 3. 为每个字符串添加上下文
		for _, text := range texts {
			text.Context = p.buildContext(lines, i, 3) // 前后3行
			results = append(results, text)
		}
	}

	return results, nil
}

// extractJapaneseText 从单行中提取日文文本（仅提取双引号包裹的日文）
func (p *NUTParser) extractJapaneseText(line string, lineNum int) []ParsedText {
	var results []ParsedText

	// 只匹配双引号包裹的日文字符串字面量
	pattern := regexp.MustCompile(`"([^"]*[^\x00-\x7F][^"]*)"`)
	matches := pattern.FindAllStringSubmatchIndex(line, -1)

	for _, match := range matches {
		if len(match) >= 4 {
			// 获取匹配的文本（不包括引号）
			text := line[match[2]:match[3]]
			start := match[0]
			end := match[1]

			// 只处理包含日文的字符串
			if containsJapanese(text) {
				results = append(results, ParsedText{
					Text:        strings.TrimSpace(text),
					LineNumber:  lineNum,
					ColumnStart: start,
					ColumnEnd:   end,
					Type:        types.TextTypeStringLiteral,
				})
			}
		}
	}

	return results
}

// buildContext 构建上下文信息
func (p *NUTParser) buildContext(lines []string, currentLine, contextLines int) string {
	start := max(0, currentLine-contextLines)
	end := min(len(lines), currentLine+contextLines+1)

	var contextBuilder strings.Builder
	for i := start; i < end; i++ {
		if i == currentLine {
			contextBuilder.WriteString(fmt.Sprintf(">>> %d: %s\n", i+1, lines[i]))
		} else {
			contextBuilder.WriteString(fmt.Sprintf("    %d: %s\n", i+1, lines[i]))
		}
	}

	return contextBuilder.String()
}

// containsJapanese 检查文本是否包含日文字符
func containsJapanese(text string) bool {
	for _, r := range text {
		// 检查是否包含日文字符范围
		if (r >= 0x3040 && r <= 0x309F) || // 平假名
			(r >= 0x30A0 && r <= 0x30FF) || // 片假名
			(r >= 0x4E00 && r <= 0x9FAF) { // 汉字
			return true
		}
	}
	return false
}

// ProcessFile 处理单个文件，将解析结果保存到数据库
func (p *NUTParser) ProcessFile(packageID uint, filePath string, content []byte) error {
	// 计算文件 hash
	hash := fmt.Sprintf("%x", sha256.Sum256(content))

	// 检查文件是否已处理
	var existingFile types.GameFile
	if p.db.Where("hash = ?", hash).First(&existingFile).Error == nil {
		return nil // 已处理过
	}

	// 创建文件记录
	gameFile := types.GameFile{
		PackageID: packageID,
		Path:      filePath,
		FileType:  types.FileTypeNUT,
		Hash:      hash,
		Size:      uint64(len(content)),
		Encoding:  "SJIS",
	}

	if err := p.db.Create(&gameFile).Error; err != nil {
		return fmt.Errorf("failed to create game file record: %w", err)
	}

	// 解析文本
	parsedTexts, err := p.ParseFile(filePath, content)
	if err != nil {
		return fmt.Errorf("failed to parse file: %w", err)
	}

	// 保存文本条目
	return p.db.Transaction(func(tx *gorm.DB) error {
		for _, parsed := range parsedTexts {
			textHash := fmt.Sprintf("%x", sha256.Sum256([]byte(parsed.Text)))

			// 查找或创建翻译记录
			var translation types.Translation
			if tx.Where("original_hash = ?", textHash).First(&translation).Error != nil {
				translation = types.Translation{
					OriginalHash: textHash,
					OriginalText: parsed.Text,
					Status:       types.TranslationStatusPending,
					UsageCount:   1,
				}
				if err := tx.Create(&translation).Error; err != nil {
					return fmt.Errorf("failed to create translation record: %w", err)
				}
			} else {
				// 增加使用计数
				if err := tx.Model(&translation).Update("usage_count", gorm.Expr("usage_count + 1")).Error; err != nil {
					return fmt.Errorf("failed to update usage count: %w", err)
				}
			}

			// 创建文本条目
			entry := types.TextEntry{
				FileID:        gameFile.ID,
				LineNumber:    parsed.LineNumber,
				ColumnStart:   parsed.ColumnStart,
				ColumnEnd:     parsed.ColumnEnd,
				OriginalText:  parsed.Text,
				TextHash:      textHash,
				Context:       parsed.Context,
				TextType:      parsed.Type,
				TranslationID: &translation.ID,
			}

			if err := tx.Create(&entry).Error; err != nil {
				return fmt.Errorf("failed to create text entry: %w", err)
			}
		}
		return nil
	})
}

// Helper functions for Go versions that don't have min/max built-ins
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
