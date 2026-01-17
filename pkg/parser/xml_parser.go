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

// XMLParser XML 文件解析器
type XMLParser struct {
	db *gorm.DB
}

// NewXMLParser 创建新的 XML 解析器
func NewXMLParser(db *gorm.DB) *XMLParser {
	return &XMLParser{db: db}
}

// XMLElement 表示 XML 元素及其上下文
type XMLElement struct {
	TagName  string
	Text     string
	LineNum  int
	Path     []string // 从根到该元素的路径
	Siblings []string // 同层标签名称
}

// ParseXMLFile 解析 XML 文件内容，提取日文字符串
func (p *XMLParser) ParseXMLFile(filePath string, content []byte) ([]ParsedText, error) {
	// 1. SJIS -> UTF-8 转换
	decoder := japanese.ShiftJIS.NewDecoder()
	utf8Content, _, err := transform.Bytes(decoder, content)
	if err != nil {
		return nil, fmt.Errorf("failed to decode SJIS content: %w", err)
	}

	var results []ParsedText
	lines := strings.Split(string(utf8Content), "\n")

	// 2. 使用正则表达式从每一行提取双引号中的日文
	pattern := regexp.MustCompile(`"([^"]*[^\x00-\x7F][^"]*)"`)

	for lineNum, line := range lines {
		matches := pattern.FindAllStringSubmatchIndex(line, -1)
		for _, match := range matches {
			if len(match) >= 4 {
				text := line[match[2]:match[3]]

				// 只处理包含日文的字符串
				if containsJapanese(text) {
					// 构建 XML 上下文
					context := p.buildXMLContext(lines, lineNum, text)

					results = append(results, ParsedText{
						Text:        strings.TrimSpace(text),
						LineNumber:  lineNum + 1,
						ColumnStart: match[0],
						ColumnEnd:   match[1],
						Type:        types.TextTypeStringLiteral,
						Context:     context,
					})
				}
			}
		}
	}

	return results, nil
}

// buildXMLContext 构建 XML 上下文信息
func (p *XMLParser) buildXMLContext(lines []string, currentLine int, text string) string {
	var contextBuilder strings.Builder

	// 添加当前行
	contextBuilder.WriteString(fmt.Sprintf(">>> %d: %s\n", currentLine+1, lines[currentLine]))

	// 向上查找外层标签
	outerTags := p.findOuterTags(lines, currentLine)
	if len(outerTags) > 0 {
		contextBuilder.WriteString("\nOuter tags:\n")
		for i, tag := range outerTags {
			indent := strings.Repeat("  ", len(outerTags)-i-1)
			contextBuilder.WriteString(fmt.Sprintf("%s%s\n", indent, tag))
		}
	}

	// 同层标签（在当前标签所在的行前后查找）
	siblingTags := p.findSiblingTags(lines, currentLine)
	if len(siblingTags) > 0 {
		contextBuilder.WriteString("\nSibling tags:\n")
		for _, tag := range siblingTags {
			contextBuilder.WriteString(fmt.Sprintf("  %s\n", tag))
		}
	}

	return contextBuilder.String()
}

// findOuterTags 找出从外到内包裹该行的所有标签
func (p *XMLParser) findOuterTags(lines []string, currentLine int) []string {
	var outerTags []string
	openCount := 0

	// 从当前行向上查找，计算未闭合的标签
	tagPattern := regexp.MustCompile(`<(/?)(\w+)[^>]*>`)

	for i := currentLine; i >= 0; i-- {
		matches := tagPattern.FindAllStringSubmatch(lines[i], -1)

		// 逆序处理该行的标签（因为我们是从下往上查找）
		for j := len(matches) - 1; j >= 0; j-- {
			match := matches[j]
			isClosing := match[1] == "/"

			if isClosing {
				openCount++
			} else {
				if openCount > 0 {
					openCount--
				} else {
					// 这是一个未闭合的开标签
					fullTag := extractTagContent(match[0])
					if !contains(outerTags, fullTag) {
						outerTags = append([]string{fullTag}, outerTags...)
					}
				}
			}
		}
	}

	return outerTags
}

// findSiblingTags 找出同层级的其他标签
func (p *XMLParser) findSiblingTags(lines []string, currentLine int) []string {
	var siblingTags []string
	tagPattern := regexp.MustCompile(`<(\w+)[^>]*>`)

	// 向上找到父标签的行
	parentLine := p.findParentTagLine(lines, currentLine)
	if parentLine < 0 {
		return siblingTags
	}

	// 在同层查找其他标签
	// 从父标签的下一行开始，到当前行为止
	for i := parentLine + 1; i < min(len(lines), currentLine+5); i++ {
		matches := tagPattern.FindAllStringSubmatch(lines[i], -1)
		for _, match := range matches {
			fullTag := extractTagContent(match[0])
			if i != currentLine && !contains(siblingTags, fullTag) {
				siblingTags = append(siblingTags, fullTag)
			}
		}
	}

	return siblingTags
}

// findParentTagLine 找出包含当前行的父标签所在的行
func (p *XMLParser) findParentTagLine(lines []string, currentLine int) int {
	openCount := 0
	tagPattern := regexp.MustCompile(`<(/?)(\w+)[^>]*>`)

	for i := currentLine; i >= 0; i-- {
		matches := tagPattern.FindAllStringSubmatch(lines[i], -1)

		for j := len(matches) - 1; j >= 0; j-- {
			match := matches[j]
			isClosing := match[1] == "/"

			if isClosing {
				openCount++
			} else {
				if openCount > 0 {
					openCount--
				} else if i < currentLine {
					return i
				}
			}
		}
	}

	return -1
}

// extractTagContent 提取标签内容（不包括括号外的内容）
func extractTagContent(fullTag string) string {
	// 简化：返回整个标签
	return strings.TrimSpace(fullTag)
}

// contains 检查字符串切片是否包含某个字符串
func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}

// ProcessXMLFile 处理单个 XML 文件，将解析结果保存到数据库
func (p *XMLParser) ProcessXMLFile(packageID uint, filePath string, content []byte) error {
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
		FileType:  types.FileTypeXML,
		Hash:      hash,
		Size:      uint64(len(content)),
		Encoding:  "SJIS",
	}

	if err := p.db.Create(&gameFile).Error; err != nil {
		return fmt.Errorf("failed to create game file record: %w", err)
	}

	// 解析文本
	parsedTexts, err := p.ParseXMLFile(filePath, content)
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
