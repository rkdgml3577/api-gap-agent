import asyncio
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from agent.graph import validate_finish, build_graph
from agent.schemas import Action, Finding
from agent.mcp_client import ToolClient
from tools.runner import run_candidate
from tools.repository import read_test_file, ROOT
from sample_service.app import create_app
from evaluation.evaluate import score


def cancel_candidate():
    return {'rule_id':'ORDER-003','description':'Shipping cancellation rejection and unchanged state','steps':[
        {'method':'POST','path':'/orders/2/cancel','user':'alice','expected_status':409},
        {'method':'GET','path':'/orders/2','user':'alice','expected_status':200,'expected_json':{'status':'shipping'}}]}


def test_real_generated_test_distinguishes_healthy_and_buggy(tmp_path):
    # Artifacts must live below ROOT, like actual runs.
    folder = ROOT / 'outputs' / uuid4().hex
    good = run_candidate('healthy', folder, cancel_candidate())
    bad = run_candidate('buggy', folder, cancel_candidate())
    assert good['status'] == 'passed'
    assert len(good['observations']) == 2
    assert bad['status'] == 'assertion_failed'
    assert bad['observations'][0]['actual_status'] == 200
    owner = run_candidate('healthy', folder, {'rule_id':'ORDER-002','description':'Representative second order access',
        'steps':[{'method':'GET','path':'/orders/2','user':'bob','expected_status':403}]})
    assert owner['status'] == 'passed'


def test_test_reader_cannot_access_evaluation_answers():
    with pytest.raises(ValueError):
        read_test_file('healthy', 'evaluation/ground_truth.json')


def test_path_is_validated_before_generation():
    with pytest.raises(ValueError):
        run_candidate('healthy', ROOT / 'outputs' / uuid4().hex,
                      {**cancel_candidate(), 'steps':[{'method':'GET','path':'http://example.com','expected_status':200}]})


def test_common_test_blocks_premature_missing_claim():
    f = Finding(rule_id='ORDER-002', coverage='missing', evidence=['file'], explanation='not found')
    observations = [{'tool':'search_tests','arguments':{},'result':{'files':[{'path':'test_common.py'}]}}]
    observations += [{'tool':'search_rules','arguments':{},'result':{}}, {'tool':'inspect_schema','arguments':{'operation_id':'get_order'},'result':{}}]
    assert 'ALL' in validate_finish([f], observations, ['get_order'])


def test_scope_guard():
    assert validate_finish([], [], ['get_order']) is not None


def _full_obs(content, exec_status='passed'):
    return [
        {'tool':'search_rules','arguments':{},'result':{'content':'rules'}},
        {'tool':'inspect_schema','arguments':{'operation_id':'get_order'},'result':{}},
        {'tool':'search_tests','arguments':{},'result':{'files':[{'path':'test_common.py'}]}},
        {'tool':'read_test_file','arguments':{'path':'test_common.py'},'result':{'path':'test_common.py','content':content}},
        {'tool':'run_candidate_test','arguments':{},'result':{'rule_id':'ORDER-002','status':exec_status,'observations':[{'actual_status':403}]}}]


def test_ungrounded_citation_is_rejected():
    # Cites a test function that does not appear in anything the agent gathered.
    f = Finding(rule_id='ORDER-002', coverage='missing', evidence=['test_phantom_owner()'],
                explanation='x', implementation='unknown')
    msg = validate_finish([f], _full_obs('def test_order_access_isolation(): ...'), ['get_order'])
    assert msg is not None and 'cite evidence' in msg


def test_grounded_citation_passes():
    # Cites a function that really appears in the read test content.
    f = Finding(rule_id='ORDER-002', coverage='missing', evidence=['test_order_access_isolation() checks 403'],
                explanation='x', implementation='conforms')
    assert validate_finish([f], _full_obs('def test_order_access_isolation(): assert r.status_code==403'), ['get_order']) is None


def test_metrics_do_not_call_missing_predictions_perfect_precision():
    result = score({'status':'completed','findings':[]}, {'missing':['ORDER-001'],'defects':[]})
    assert result['precision'] is None
    assert result['recall'] == 0


def test_existing_tests_really_enforce_owner_rule():
    with TestClient(create_app()) as client:
        assert client.get('/orders/1', headers={'X-User':'bob'}).status_code == 403


def test_mcp_round_trip():
    async def run():
        async with ToolClient() as tools:
            names = {t['name'] for t in await tools.catalog()}
            assert 'run_candidate_test' in names
            result = await tools.call('search_tests', {'variant':'covered'})
            assert len(result['files']) == 3
    asyncio.run(run())


def test_graph_revises_premature_finish_using_tool_observation():
    class Model:
        def __init__(self): self.count = 0
        async def choose(self, context):
            self.count += 1
            if self.count == 1:
                return Action(reason='Need access tests', tool='search_tests', arguments={})
            if self.count == 2:
                return Action(reason='Try finishing without reading', tool='finish', findings=[Finding(rule_id='ORDER-002', coverage='missing', evidence=['tests'], explanation='missing')])
            if self.count == 3:
                assert context['observations'][-1]['tool'] == 'finish_validation'
                return Action(reason='Read common test', tool='read_test_file', arguments={'path':'common.py'})
            return Action(reason='Common test covers access', tool='assess_coverage' if self.count == 4 else 'finish', findings=[Finding(rule_id='ORDER-002', coverage='covered', evidence=['common.py:1'], explanation='403 assertion exists')])
    class Tools:
        async def call(self, name, args):
            if name == 'search_tests': return {'files':[{'path':'common.py'}]}
            return {'path':'common.py','content':'1: assert response.status_code == 403'}
    async def run():
        events=[]
        async def emit(e): events.append(e)
        graph=build_graph(Model(), Tools(), [], {'goal':'check','operations':['get_order'],'variant':'healthy'}, uuid4().hex, emit)
        state=await graph.ainvoke({'steps':0,'observations':[{'tool':'search_rules','arguments':{},'result':{}}, {'tool':'inspect_schema','arguments':{'operation_id':'get_order'},'result':{}}]})
        assert state['result']['findings'][0]['coverage'] == 'covered'
        assert any(e['type']=='revision' for e in events)
    asyncio.run(run())


def test_runner_rejects_invented_error_response_fields():
    candidate = cancel_candidate()
    candidate['steps'][0]['expected_json'] = {'error': 'invented'}
    with pytest.raises(ValueError):
        run_candidate('healthy', ROOT / 'outputs' / uuid4().hex, candidate)


def test_http_analysis_sse_and_saved_report(monkeypatch):
    import server
    class Model:
        model = 'integration-test-double'
        tokens = 0
        def __init__(self): self.count = 0
        async def choose(self, context):
            sequence = [
                Action(reason='Read rules', tool='search_rules'),
                Action(reason='Read schema', tool='inspect_schema', arguments={'operation_id':'get_order'}),
                Action(reason='Find existing tests', tool='search_tests'),
                Action(reason='Read common assertions', tool='read_test_file', arguments={'path':'sample_service/tests/test_common_access.py'}),
                Action(reason='Check other original tests', tool='read_test_file', arguments={'path':'sample_service/tests/test_orders.py'}),
                Action(reason='Record original coverage', tool='assess_coverage', findings=[Finding(rule_id='ORDER-002',coverage='covered',evidence=['sample_service/tests/test_common_access.py:8'],explanation='403 assertion exists')]),
                Action(reason='Existing assertion covers rule', tool='finish', findings=[Finding(rule_id='ORDER-002',coverage='covered',evidence=['data/rules/order_rules.md:7','sample_service/tests/test_common_access.py:8'],explanation='Other owner receives 403')])]
            action=sequence[self.count]
            self.count+=1
            return action
    monkeypatch.setattr(server, 'OllamaLLM', Model)
    with TestClient(server.app) as client:
        response=client.post('/analyses', json={'operations':['get_order']})
        assert response.status_code == 202
        run_id=response.json()['run_id']
        with client.stream('GET', f'/analyses/{run_id}/events') as events:
            text=''.join(events.iter_text())
        assert '"type": "final"' in text
        report=client.get(f'/analyses/{run_id}').json()
        assert report['result']['status']=='completed'
        assert report['result']['findings'][0]['coverage']=='covered'
        assert (ROOT/'outputs'/run_id/'report.json').is_file()


def test_model_action_schema_restricts_paths_and_tool_arguments():
    from agent.llm import action_schema
    from jsonschema import validate, ValidationError
    context={'available_tools':['read_test_file','inspect_schema'],
             'progress':{'unread_test_files':['common.py'],'uninspected_operations':['get_order']},
             'tools':[{'name':'read_test_file','parameters':{'type':'object','properties':{'variant':{'type':'string'},'path':{'type':'string'}},'required':['variant','path']}},
                      {'name':'inspect_schema','parameters':{'type':'object','properties':{'operation_id':{'type':'string'}},'required':['operation_id']}}]}
    schema=action_schema(context)
    validate({'tool':'read_test_file','arguments':{'path':'common.py'},'reason':'Read remaining test'},schema)
    with pytest.raises(ValidationError):
        validate({'tool':'read_test_file','arguments':{'path':'already_read.py'},'reason':'Repeat'},schema)
    with pytest.raises(ValidationError):
        validate({'tool':'inspect_schema','arguments':{'path':'common.py'},'reason':'Wrong arguments'},schema)


def test_covered_must_cite_a_test_not_the_rules_doc():
    observations = [
        {'tool':'search_rules','arguments':{},'result':{'content':'ORDER-001 QUANTITYBOUND is 1..100'}},
        {'tool':'inspect_schema','arguments':{'operation_id':'create_order'},'result':{}},
        {'tool':'search_tests','arguments':{},'result':{'files':[{'path':'t.py'}]}},
        {'tool':'read_test_file','arguments':{'path':'t.py'},'result':{'path':'t.py','content':'def test_other(): pass'}}]
    f = Finding(rule_id='ORDER-001', coverage='covered', evidence=['QUANTITYBOUND per the rules'],
                explanation='x', implementation='unknown')
    msg = validate_finish([f], observations, ['create_order'])
    assert msg is not None and 'covered verdict must cite an existing TEST' in msg


def test_rag_top_k_ranks_by_similarity():
    from agent.retrieval import top_k
    vocab = ["order", "payment"]
    embed = lambda texts: [[t.count("order"), t.count("payment")] for t in texts]
    items = [("r1", "order order"), ("r2", "payment"), ("r3", "order")]
    assert top_k("order order", items, 2, embed=embed) == ["r1", "r3"]
    assert top_k("order", items, 0, embed=embed) == ["r1", "r2", "r3"]  # k<=0 -> all


def test_conflict_detector_flags_contradictory_bounds():
    from agent.graph import detect_rule_conflicts
    assert detect_rule_conflicts("## ORDER-001\n수량은 1~100. 단 상한은 50이다.") == {"ORDER-001"}
    assert detect_rule_conflicts("## ORDER-001\n수량은 1~100(양 끝 포함). 0과 101은 거절.") == set()


def test_conflicted_rule_must_be_uncertain():
    obs = [
        {'tool':'search_rules','arguments':{},'result':{'content':'## ORDER-002\n값은 1~100. 단 상한은 50.'}},
        {'tool':'inspect_schema','arguments':{'operation_id':'get_order'},'result':{}},
        {'tool':'search_tests','arguments':{},'result':{'files':[{'path':'t.py'}]}},
        {'tool':'read_test_file','arguments':{'path':'t.py'},'result':{'path':'t.py','content':'def test_order_access_isolation(): pass'}}]
    f = Finding(rule_id='ORDER-002', coverage='missing', evidence=['test_order_access_isolation()'],
                explanation='x', implementation='unknown')
    msg = validate_finish([f], obs, ['get_order'])
    assert msg is not None and 'uncertain' in msg
    # same rule as uncertain → conflict guard passes
    f2 = Finding(rule_id='ORDER-002', coverage='uncertain', evidence=['test_order_access_isolation()'],
                 explanation='x', implementation='unknown')
    assert validate_finish([f2], obs, ['get_order']) is None


def test_approval_policy_triggers_only_on_high_stakes():
    from agent.approval import review_reasons
    assert review_reasons([{'rule_id':'ORDER-003','coverage':'missing','implementation':'violates'}])
    assert review_reasons([{'rule_id':'ORDER-002','coverage':'uncertain','implementation':'unknown'}])
    assert review_reasons([{'rule_id':'ORDER-001','coverage':'covered','implementation':'unknown'}]) == []


def test_human_approver_auto_passes_routine_results():
    from agent.approval import HumanApprover
    async def emit(e): pass
    async def run():
        ha = HumanApprover('r', emit, {})  # empty store; must NOT wait on a future
        findings = [{'rule_id':'ORDER-001','coverage':'covered','implementation':'unknown'}]
        return await asyncio.wait_for(ha.review(findings, {}), timeout=1)
    decision = asyncio.run(run())
    assert decision['approved'] and decision['by'] == 'policy-auto'


def test_approval_gate_rejects_then_approves():
    # Model keeps proposing the same valid finish; approver rejects once, then approves.
    class Model:
        async def choose(self, context):
            return Action(tool='finish', reason='Report', findings=[Finding(
                rule_id='ORDER-001', coverage='missing', evidence=['test_create_order() uses quantity=2'],
                explanation='boundary missing', implementation='conforms')])
    class StubApprover:
        def __init__(self): self.calls=0
        async def review(self, findings, context):
            self.calls+=1
            if self.calls==1:
                return {"approved": False, "feedback": "cite the boundary you executed", "by": "human"}
            return {"approved": True, "feedback": "", "by": "human"}
    async def run():
        observations=[
            {'tool':'search_rules','arguments':{},'result':{'content':'rules'}},
            {'tool':'inspect_schema','arguments':{'operation_id':'create_order'},'result':{}},
            {'tool':'search_tests','arguments':{},'result':{'files':[{'path':'original.py'}]}},
            {'tool':'read_test_file','arguments':{'path':'original.py'},'result':{'path':'original.py','content':'def test_create_order(): quantity=2'}},
            {'tool':'run_candidate_test','arguments':{},'result':{'rule_id':'ORDER-001','status':'passed','observations':[{'actual_status':400}]}}]
        original=Finding(rule_id='ORDER-001',coverage='missing',evidence=['original.py:1'],explanation='only quantity=2').model_dump()
        events=[]
        async def emit(e): events.append(e)
        approver=StubApprover()
        graph=build_graph(Model(),None,[],{'goal':'check','operations':['create_order'],'variant':'healthy'},uuid4().hex,emit,approver)
        state=await graph.ainvoke({'steps':0,'observations':observations,'coverage':[original]})
        assert approver.calls==2
        assert state['result']['status']=='completed'
        assert state['result']['approval']['by']=='human'
        assert any(e['type']=='revision' and 'Reviewer rejected' in e['message'] for e in events)
    asyncio.run(run())


def test_new_passing_test_cannot_erase_original_coverage_gap():
    class Model:
        def __init__(self): self.count=0
        async def choose(self, context):
            self.count+=1
            return Action(tool='finish', reason='Report execution', findings=[Finding(
                rule_id='ORDER-001', coverage='covered' if self.count == 1 else 'missing',
                evidence=['original.py:6'], explanation='Generated boundary checks pass',
                implementation='conforms')])
    async def run():
        observations=[
            {'tool':'search_rules','arguments':{},'result':{}},
            {'tool':'inspect_schema','arguments':{'operation_id':'create_order'},'result':{}},
            {'tool':'search_tests','arguments':{},'result':{'files':[{'path':'original.py'}]}},
            {'tool':'read_test_file','arguments':{'path':'original.py'},'result':{'path':'original.py','content':'quantity=2 only'}},
            {'tool':'run_candidate_test','arguments':{},'result':{'rule_id':'ORDER-001','status':'passed','observations':[{'actual_status':400}]}}]
        original=Finding(rule_id='ORDER-001',coverage='missing',evidence=['original.py:1'],explanation='Existing tests only use quantity=2').model_dump()
        events=[]
        async def emit(e): events.append(e)
        graph=build_graph(Model(),None,[],{'goal':'check','operations':['create_order'],'variant':'healthy'},uuid4().hex,emit)
        state=await graph.ainvoke({'steps':0,'observations':observations,'coverage':[original]})
        result=state['result']['findings'][0]
        assert result['coverage']=='missing'
        assert result['implementation']=='conforms'
        assert result['explanation']=='Existing tests only use quantity=2'
        assert any(e['type']=='revision' for e in events)
    asyncio.run(run())
