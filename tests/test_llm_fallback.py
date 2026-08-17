"""LLM provider fallback, validation, and robustness tests."""
from __future__ import annotations

from app.ai.llm import LocalProvider, get_llm_provider
from app.ai.rag import CoachService, detect_intent
from app.utils import safe_json, split_list


def test_local_provider_available_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = get_llm_provider(force="local")
    assert provider.available() is True
    out = provider.complete("system", "LEARNER QUESTION: hi", max_tokens=50)
    assert "local_fallback" in out


def test_openai_provider_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.ai.llm import OpenAIProvider

    provider = OpenAIProvider()
    assert provider.available() is False


def test_auto_provider_falls_back_to_local(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.ai.llm import _provider, LocalProvider

    global _provider  # noqa: F811
    _provider = None
    provider = get_llm_provider(force="auto")
    assert isinstance(provider, LocalProvider)


def test_safe_json_tolerates_garbage():
    assert safe_json("not json at all") is None
    assert safe_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert safe_json("Here is the result: {\"b\": 2} thanks!") == {"b": 2}
    assert safe_json(None) is None
    assert safe_json("{\"broken\": ") is None


def test_split_list_normalization():
    assert split_list("a;b,c") == ["a", "b", "c"]
    assert split_list(["x", "y;z"]) == ["x", "y", "z"]
    assert split_list(None) == []
    assert split_list("") == []


def test_intent_detection():
    assert detect_intent("What should I do today?") == "mission"
    assert detect_intent("whats next") == "next"
    assert detect_intent("Can I skip statistics?") == "skip"
    assert detect_intent("Why should I learn SQL?") == "why_skill"
    assert detect_intent("I'm struggling with classification") == "struggling"
    assert detect_intent("Explain cross-validation") == "explain"
    assert detect_intent("I just finished the course") == "completed"
    assert detect_intent("tell me about cloud stuff") == "explain"


def test_coach_honesty_on_unknown_topic(engine, ml_learner):
    learner, roadmap = ml_learner
    coach = CoachService(engine.catalog, engine.graph)
    reply = coach.chat(learner, roadmap, "Explain the mating habits of capybaras")
    assert reply.intent == "explain"
    # must admit it doesn't know instead of hallucinating
    assert "don't have" in reply.text.lower() or "knowledge base" in reply.text.lower()


def test_coach_rag_retrieves_real_facts(engine, ml_learner):
    learner, roadmap = ml_learner
    coach = CoachService(engine.catalog, engine.graph)
    reply = coach.chat(learner, roadmap, "Explain cross-validation")
    assert reply.intent == "explain"
    assert "cross-validation" in reply.text.lower()
    assert len(reply.sources) >= 1  # retrieved real knowledge-base chunks
    assert reply.sources[0].startswith(("skill:", "course:", "resource:", "assessment:"))


def test_coach_mission_uses_roadmap(engine, ml_learner):
    learner, roadmap = ml_learner
    coach = CoachService(engine.catalog, engine.graph)
    reply = coach.chat(learner, roadmap, "What should I do today?")
    assert reply.intent == "mission"
    assert "minutes" in reply.text
