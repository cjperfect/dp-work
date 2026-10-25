import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import create_app


def test_documentation_routes_and_authentication_contract():
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            docs = await client.get("/api/docs")
            assert docs.status_code == 200
            assert "/api/openapi.json" in docs.text
            assert (await client.get("/api/redoc")).status_code == 200
            response = await client.get("/api/openapi.json")
            assert response.status_code == 200
            schema = response.json()
            assert "/api/auth/users/me" not in schema["paths"]
            bearer = schema["components"]["securitySchemes"]["BearerAuth"]
            assert bearer["type"] == "http" and bearer["scheme"] == "bearer"
            for path, operations in schema["paths"].items():
                assert not path.startswith("/api/v1/")
                for operation in operations.values():
                    assert {code for code in operation["responses"] if code.startswith("2")} == {"200"}
            for path in ("/api/auth/login", "/api/auth/register"):
                assert not schema["paths"][path]["post"].get("security")
            for path, method in (("/api/knowledge-bases", "post"),):
                assert schema["paths"][path][method]["security"] == [{"BearerAuth": []}]

    asyncio.run(case())
