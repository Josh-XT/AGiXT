from ApiClient import DB_CONNECTED

if __name__ == "__main__":
    if DB_CONNECTED:
        from db.imports import (
            import_extensions,
            import_prompts,
            import_providers,
            import_agents,
            import_chains,
            import_conversations,
        )

        import_extensions()
        import_prompts()
        import_providers()
        import_agents()
        import_chains()
        import_conversations()
