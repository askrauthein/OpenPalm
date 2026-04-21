from openpalm.oneoff_runner import _extract_answer, _extract_tokens


def test_extract_answer_and_tokens_codex_style_output():
    raw = '''OpenAI Codex v0.121.0\nuser\nqual a circunferencia da terra?\ncodex\nA circunferência da Terra é aproximadamente:\n\n- 40.075 km no equador\n- 40.008 km passando pelos polos\n\ntokens used\n16,248\n'''
    answer = _extract_answer(raw, 'codex')
    tokens = _extract_tokens(raw)
    assert answer.startswith('A circunferência da Terra é aproximadamente:')
    assert 'tokens used' not in answer.lower()
    assert tokens == 16248
