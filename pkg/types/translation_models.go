package types

import (
	"time"

	"gorm.io/gorm"
)

// GamePackage 表示一个游戏资源包或版本
type GamePackage struct {
	ID        uint      `gorm:"primaryKey"`
	Name      string    `gorm:"size:255;not null;uniqueIndex"`
	Version   string    `gorm:"size:64"`
	Path      string    `gorm:"size:1024"` // 包文件路径
	CreatedAt time.Time
	UpdatedAt time.Time

	// 关联
	Files []GameFile `gorm:"foreignKey:PackageID"`
}

// GameFile 表示游戏中的一个文件（专注汉化需求的简化版）
type GameFile struct {
	ID          uint           `gorm:"primaryKey"`
	PackageID   uint           `gorm:"index;not null"`
	Path        string         `gorm:"size:1024;not null;index"` // 相对路径，如 "BTL_ISR/BTL_ISR_Q1.NUT"
	FileType    string         `gorm:"size:32;index"`            // "NUT", "XML", etc.
	Hash        string         `gorm:"size:64;uniqueIndex"`      // 文件内容 SHA256
	Size        uint64
	Encoding    string         `gorm:"size:32;default:'SJIS'"`
	CreatedAt   time.Time
	UpdatedAt   time.Time
	DeletedAt   gorm.DeletedAt `gorm:"index"`

	// 关联
	Package     GamePackage `gorm:"foreignKey:PackageID"`
	TextEntries []TextEntry `gorm:"foreignKey:FileID"`
}

// TextEntry 表示文件中的一个日文文本条目
type TextEntry struct {
	ID              uint           `gorm:"primaryKey"`
	FileID          uint           `gorm:"index;not null"`
	LineNumber      int            `gorm:"index"`                    // 在文件中的行号
	ColumnStart     int            // 字符串在行中的起始位置
	ColumnEnd       int            // 字符串在行中的结束位置
	OriginalText    string         `gorm:"type:text;not null"`       // 原始日文
	TextHash        string         `gorm:"size:64;index"`            // 原文 SHA256，用于去重
	Context         string         `gorm:"type:text"`                // 上下文（前后几行）
	TextType        string         `gorm:"size:64;index"`            // "comment", "string_literal", "function_call", etc.
	TranslationID   *uint          `gorm:"index"`                    // 指向翻译记录
	CreatedAt       time.Time
	UpdatedAt       time.Time
	DeletedAt       gorm.DeletedAt `gorm:"index"`

	// 关联
	File        GameFile     `gorm:"foreignKey:FileID"`
	Translation *Translation `gorm:"foreignKey:TranslationID"`
}

// Translation 表示翻译记录（去重核心）
type Translation struct {
	ID              uint           `gorm:"primaryKey"`
	OriginalHash    string         `gorm:"size:64;uniqueIndex;not null"` // 原文 hash
	OriginalText    string         `gorm:"type:text;not null"`
	TranslatedText  string         `gorm:"type:text"`
	Status          string         `gorm:"size:32;default:'pending';index"` // pending, translated, reviewed, approved
	Translator      string         `gorm:"size:255"`
	Reviewer        string         `gorm:"size:255"`
	Notes           string         `gorm:"type:text"`
	Priority        int            `gorm:"default:0;index"`              // 翻译优先级
	UsageCount      int            `gorm:"default:0"`                    // 被引用次数
	CreatedAt       time.Time
	UpdatedAt       time.Time
	DeletedAt       gorm.DeletedAt `gorm:"index"`

	// 关联
	TextEntries []TextEntry `gorm:"foreignKey:TranslationID"`
}

// TranslationProject 表示翻译项目/批次管理
type TranslationProject struct {
	ID          uint      `gorm:"primaryKey"`
	Name        string    `gorm:"size:255;not null"`
	Description string    `gorm:"type:text"`
	Status      string    `gorm:"size:32;default:'active'"`
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

// TranslationStatus 定义翻译状态常量
const (
	TranslationStatusPending   = "pending"
	TranslationStatusDraft     = "draft"
	TranslationStatusTranslated = "translated"
	TranslationStatusReviewed  = "reviewed"
	TranslationStatusApproved  = "approved"
	TranslationStatusRejected  = "rejected"
)

// TextType 定义文本类型常量
const (
	TextTypeComment       = "comment"
	TextTypeStringLiteral = "string_literal"
	TextTypeFunctionCall  = "function_call"
	TextTypeVariable      = "variable"
	TextTypeOther         = "other"
)

// FileType 定义文件类型常量
const (
	FileTypeNUT = "NUT"
	FileTypeXML = "XML"
	FileTypeTXT = "TXT"
)