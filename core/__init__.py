"""RwSaveTool 核心包：路径、存档读取、模组只读导入、导入缓存、前端桥接。"""

__all__ = ["paths", "save_io", "mod_importer", "region_store", "bridge"]
# 程序版本：唯一来源。改这里即可，bridge 与窗口标题都从这里取。
# 语义化版本：主版本.次版本.修订号；配置结构版本另见 paths.CONFIG_VERSION。
__version__ = "1.0.0"

# 版本名称与发布日期（随版本号一起更新，供「关于」与发布包元信息使用）
__version_name__ = "可分发基线版"
__release_date__ = "2026-11-06"
