from haytile.db import normalize_database_url


def test_render_postgres_urls_select_the_installed_psycopg_driver():
    assert (
        normalize_database_url("postgres://test:fixture@db/haytile")
        == "postgresql+psycopg://test:fixture@db/haytile"
    )
    assert (
        normalize_database_url("postgresql://test:fixture@db/haytile?sslmode=require")
        == "postgresql+psycopg://test:fixture@db/haytile?sslmode=require"
    )
    assert (
        normalize_database_url("postgresql+psycopg://db/haytile")
        == "postgresql+psycopg://db/haytile"
    )
    assert normalize_database_url("sqlite:///test.db") == "sqlite:///test.db"
