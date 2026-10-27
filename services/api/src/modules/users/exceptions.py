class UsernameExistsError(Exception):
    """用户名冲突，禁止返回已存在账号的身份。"""
