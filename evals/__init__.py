"""에이전트 평가/회귀 하네스.

production(app/) 코드는 건드리지 않고 monkeypatch 로만 LLM·도구·알림을 가로채
라우팅·도구 계약(결정론)과 출력 품질(LLM-judge)을 평가한다.
"""
