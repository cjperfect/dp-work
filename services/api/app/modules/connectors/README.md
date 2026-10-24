# connectors

连接器授权关系、操作策略与审计；第三方调用放在 infrastructure/integrations。

当前为预留模块，尚未实现接口。新增能力时按需添加 router.py、schemas.py、service.py、repository.py、models.py。
路由只处理 HTTP；跨模块通过 Service 调用，不直接访问其他模块 Repository。
