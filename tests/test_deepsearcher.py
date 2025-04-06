
def test_deepsearcher():
    from deep_searcher import AgentDeepSearch

    agent = AgentDeepSearch()

    query = "Explain the concept of reinforcement learning."

    result = agent.run(query)

    assert isinstance(result, str), "Result should be a string"
    assert len(result) > 0, "Result should not be empty"
    assert "reinforcement learning" in result, "Result should contain the query term"
