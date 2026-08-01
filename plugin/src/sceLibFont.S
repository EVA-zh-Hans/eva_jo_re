	.set noreorder

#include "pspimport.s"

#ifdef F_sceLibFont_0000
	IMPORT_START "sceLibFont",0x00090011
#endif
#ifdef F_sceLibFont_0014
	IMPORT_FUNC "sceLibFont",0x57FCB733,sceFontOpenUserFile
#endif
