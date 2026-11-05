"""Read-only, task-local search and scripted clarification for the v2 candidate.

This module has no network client, filesystem tool, grader import or model judge.
"""
import argparse
import json
import re
from pathlib import Path, PurePosixPath

TOOL_NAMES = ('list_files', 'search_files', 'read_file', 'ask_requester')

def initial_message(task):
    return task['prompt'] + '\nATTACHED CONTENT\n' + json.dumps(task['attachments'], ensure_ascii=False) + '\nAUDIT FIELD NAMES\n' + json.dumps(task['fact_keys'])

class Workspace:
    def __init__(self, task):
        self.files = dict(task['workspace'])
        self.clarifications = list(task.get('clarifications', []))
        self.events = []

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            reply = {'error': 'arguments_must_be_object'}
        else:
            try:
                reply = self._dispatch(name, arguments)
            except (TypeError, ValueError):
                reply = {'error': 'invalid_arguments'}
        self.events.append({'tool': name, 'arguments': arguments, 'reply': reply})
        return reply

    def _dispatch(self, name, args):
        if name == 'list_files':
            prefix = args.get('prefix', '')
            if not isinstance(prefix, str) or '..' in PurePosixPath(prefix).parts or prefix.startswith('/'):
                return {'error': 'invalid_prefix'}
            return {'files': [p for p in sorted(self.files) if p.startswith(prefix)]}
        if name == 'read_file':
            path = args.get('path')
            if not isinstance(path, str) or path.startswith('/') or '..' in PurePosixPath(path).parts or path not in self.files:
                return {'error': 'file_not_in_this_workspace'}
            return {'path': path, 'content': self.files[path]}
        if name == 'search_files':
            query = args.get('query', '')
            if not isinstance(query, str) or not query.strip() or len(query) > 300:
                return {'error': 'query_required_max_300_characters'}
            terms = set(re.findall(r'[\w]+', query.casefold()))
            if not terms:
                return {'results': []}
            hits = []
            for path, content in self.files.items():
                haystack = (path + ' ' + content).casefold()
                score = sum(term in haystack for term in terms)
                if score:
                    positions = [content.casefold().find(term) for term in terms if term in content.casefold()]
                    start = max(0, min(positions, default=0)-45)
                    hits.append((score, path, content[start:start+260]))
            hits.sort(key=lambda x: (-x[0], x[1]))
            return {'results': [{'path': p, 'snippet': s} for _, p, s in hits[:5]], 'total_matches': len(hits)}
        if name == 'ask_requester':
            question = args.get('question', '')
            if not isinstance(question, str) or not question.strip() or len(question) > 1000:
                return {'error': 'specific_question_required'}
            words = set(re.findall(r'[\w]+', question.casefold()))
            matches = [x for x in self.clarifications if any(k in words for k in x['keywords'])]
            if len(matches) == 1:
                return {'source': 'scripted_requester_confirmation', 'topic': matches[0]['topic'], 'answer': matches[0]['reply'], 'new_approval_granted': False}
            return {'source': 'scripted_requester', 'answer': 'No additional confirmed information is available for that question. Do not infer a new approval, capacity commitment, or appointment.', 'new_approval_granted': False}
        return {'error': 'unknown_tool'}

def main():
    parser = argparse.ArgumentParser(description='Offline workspace demonstration; no model calls.')
    parser.add_argument('instance')
    parser.add_argument('tool', choices=TOOL_NAMES)
    parser.add_argument('arguments', nargs='?', default='{}')
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1]/'data/paired_v2/solver'/(args.instance+'.json')
    if path.parent.name != 'solver' or '/' in args.instance or '\\' in args.instance:
        raise SystemExit('Use an instance ID, not a path')
    print(json.dumps(Workspace(json.loads(path.read_text())).call(args.tool, json.loads(args.arguments)), indent=2))

if __name__ == '__main__':
    main()
