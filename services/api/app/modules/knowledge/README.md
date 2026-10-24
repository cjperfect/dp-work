# knowledge

知识库权限、文档版本、分块与检索。会议入库通过此模块的 Service 接口。

当前为预留模块，尚未实现接口。新增能力时按需添加 router.py、schemas.py、service.py、repository.py、models.py。
路由只处理 HTTP；跨模块通过 Service 调用，不直接访问其他模块 Repository。
