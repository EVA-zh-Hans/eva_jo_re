# 文件构成
+ 末尾是文件夹的索引
+ 中间是文件的索引
+ 开头是具体的文件

+ 文件可能采取DEFLATE算法压缩，视文件头部而定

索引的数据结构参见`GitHub`，分析基本正确，但`NUT`似乎拥有子文件夹

```C
struct Param1
{
  int unk0;
  int unk1;
  int unk2;
  char* pkg_buffer; // NEVA.PKG读向的缓冲区
  char *buffer;
  int unk5;
  int size; // 文件大小
  int pkg_whence;   // NEVA.PKG中BDL0的偏移量
  int pkg_buf_size; // 从NEVA.PKG读入时的缓冲区大小（在Entry中为第二个u32）
  int fd;   // fd
  int pkg_fd; // NEVA.PKG的fd
  char name[256]; // 文件名
  int unk9; // Flag
};
```

# 所有文件读取似乎均经过此处
```C
int __fastcall sub_898B380(int a1, int a2, char a3)
{
  int v5; // $v0
  int v6; // $a0

  *(_BYTE *)(a1 + 301) = a3;
  *(_BYTE *)a1 = 0;
  v5 = sub_898ABD4(a2);
  *(_DWORD *)(a1 + 4) = v5;
  if ( v5 )
    return 1;
  sub_89E8A58(a1 + 44, a2);
  v6 = sub_898AFF8(a2);
  *(_DWORD *)(a1 + 8) = v6;
  if ( v6 )
  {
    *(_DWORD *)(a1 + 24) = sub_898D2B8();
    return 1;
  }
    // 这个函数似乎是在判断NEVA.PKG是否已打开
    // bool FUN_0898aad0(void)
    // return DAT_08aa2740 != 0;
  else if ( sub_898AAD0() )
  {
    // 似乎往往进入此处？
    return sub_898C9F8(a1, a2);
  }
  else
  {
    // 此处将直接打开文件
	// 经过修改，确实可以，但是同时打开的文件数目过多，fd数目爆炸了……
    return sub_898BA34(a1, a2, 1u);
  }
}
```

`898ba34`开始似乎调用了898ade0来计算目标地址。

```C
/**
计算目标文件地址，选择从disc0 / ms0 / host0 读取
**/
int __fastcall sub_898ADE0(int a1, const char *a2, char a3)
{
  const char *v5; // $a0
  const char *v6; // $a2
  int result; // $v0
  int v8; // $a3
  char *i; // $a5
  char v10[256]; // [sp+0h] [-100h] BYREF

  v5 = a2;
  if ( a3 )
    v6 = &byte_8ABE578;
  else
    v6 = (const char *)off_8AA27C0;
  if ( dword_8AA2700 > 0 )
  {
    if ( dword_8AA2700 < 2 )
    {
      v8 = *a2;
      for ( i = v10; *v5; ++i )
      {
        if ( (byte_8A88F91[v8] & 2) != 0 )
          LOBYTE(v8) = v8 - 32;
        *i = v8;
        v8 = *++v5;
      }
      *i = 0;
       // 该值为0.
       // 这里v10已经大写了
      return sub_89E8278(a1, "disc0:/PSP_GAME/USRDIR/%s%s", v6, v10);
    }
    else if ( dword_8AA2700 < 3 )
    {
	    // 这里似乎不会
      return sub_89E8278(a1, "ms0:NEVA/%s%s", v6, a2);
    }
  }
  else if ( dword_8AA2700 >= 0 )
  {
    return sub_89E8278(a1, "host0:%s%s", v6, a2);
  }
  return result;
}
```

# 加载文件：sub_898B520
```C
int __fastcall sub_898B520(Param1 *a1, unsigned __int8 a2, int a3, int a4, int a5, int a6, int a7, int a8)
{
  int unk1; // $a2
  int v9; // $s1
  int result; // $v0
  char *buffer; // $a0
  int unk2; // $a0
  char *v14; // $v0
  int fd; // $a0
  int v16; // $v0
  int v17; // $a2
  int v18; // $a3
  int v19; // $a4
  int v20; // $a5
  int v21; // $a6
  int v22; // $a7

  unk1 = a1->unk1;
  v9 = a2;
  if ( unk1 )
    return 1;
  if ( dword_8AA2704 )
    dword_8AA2704();
  if ( !LOBYTE(a1->unk9) )
  {
    buffer = a1->buffer;
    if ( buffer )
      sub_89E8570((int)buffer);
  }
  if ( v9 )
  {
    unk2 = a1->unk2;
LABEL_16:
    LOBYTE(a1->unk9) = v9;
    if ( unk2 && (v16 = sub_898AFF8(a1->name), (a1->unk2 = v16) != 0) )
    {
      if ( v9 )
      {
        sub_898AAE0();
        a1->buffer = (char *)dword_8AA270C;
      }
      // unk2 seems to be another pointer to some struct
      if ( sub_898D3B4(a1->unk2, a1->buffer, a1->size) )
        a1->buffer[a1->size] = 0;
      return 1;
    }
    else if ( a1->fd >= 0 )
    {
      if ( v9 )
      {
        sub_898AAE0();
        a1->buffer = (char *)dword_8AA270C;
      }
      // 直接读取文件
      sub_89E8218("[FILE LOADING]:%s\n", (int)a1->name, unk1, a4, a5, a6, a7, a8);
      sceIoLseek(a1->fd, (int)"gmanHideLayerAll", 0);
      sceIoRead(a1->fd, a1->buffer, a1->size);
      sceIoClose(a1->fd);
      a1->buffer[a1->size] = 0;
      a1->fd = -1;
      return 1;
    }
    else if ( sub_898AAD0() )
    {
      sub_89E8218("[FILE LOADING]:%s\n", (int)a1->name, v17, v18, v19, v20, v21, v22);
      // 从PKG里读取
      result = sub_898CAF0((int)a1, (int)a1->buffer, a1->size, 0);
      if ( result )
        a1->buffer[a1->size] = 0;
    }
    else
    {
      return 0;
    }
    return result;
  }
  v14 = (char *)sub_89E8524(4, a1->size + 1);
  a1->buffer = v14;
  if ( v14 )
  {
    unk2 = a1->unk2;
    goto LABEL_16;
  }
  fd = a1->fd;
  if ( fd >= 0 )
    sceIoClose(fd);
  a1->fd = -1;
  return 0;
}
```


- **`dword_8AA270C`**  
    预定义的静态缓冲区基地址。若存在，优先用于存储数据，避免动态分配。
    
- **`dword_8AA272C`**  
    异步读取的临时缓冲区地址，数据先读至此，再复制到`pkg_buffer`。
    
- **`dword_8AA273C`**  
    传递给`sub_898C0C0`的参数，为文件路径。

TODO: 鉴于NUT文件大小不大，似乎可以考虑仅解压缩这一部分文件，其余部分保持不解压。