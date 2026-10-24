# skills

Skill 版本、发布和分配。内置技能内容与安装产物分开管理。

当前为预留模块，尚未实现接口。新增能力时按需添加 router.py、schemas.py、service.py、repository.py、models.py。
路由只处理 HTTP；跨模块通过 Service 调用，不直接访问其他模块 Repository。
