# These files are corpus text for the agent to investigate, not runnable tests:
# they import an app that does not exist on purpose. Keep pytest from collecting them.
collect_ignore_glob = ["test_*.py"]
