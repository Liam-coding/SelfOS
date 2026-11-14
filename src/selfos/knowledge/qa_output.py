"""Validate model-selected IDs; derive citation provenance only from retained data."""
import copy


def validate_answer(payload, selected):
    if not isinstance(payload, dict) or set(payload) != {'status', 'answer', 'record_ids', 'inferences'}:
        raise ValueError('Answer requires status, answer, record_ids and inferences only')
    status, answer, identities, inferences = (payload[key] for key in ('status', 'answer', 'record_ids', 'inferences'))
    if status not in ('answered', 'insufficient_evidence') or not isinstance(answer, str) or len(answer) > 1500:
        raise ValueError('Invalid answer status or summary length')
    if (not isinstance(identities, list) or len(identities) > 8
            or any(not isinstance(identity, str) for identity in identities)
            or len(set(identities)) != len(identities)
            or not isinstance(inferences, list) or len(inferences) > 3):
        raise ValueError('Invalid answer references or inferences')
    if status == 'insufficient_evidence':
        if identities or inferences:
            raise ValueError('Insufficient evidence cannot contain attributed claims')
        return dict(status=status, answer='', answer_kind='insufficient_evidence', references=[], inferences=[])
    allowed = {row['record']['id']: row for row in selected}
    if not answer.strip() or not identities or any(identity not in allowed for identity in identities):
        raise ValueError('Answered summary needs admitted record IDs')
    normalized_inferences = []
    for inference in inferences:
        if not isinstance(inference, dict) or set(inference) != {'text', 'record_ids'}:
            raise ValueError('Inference requires text and admitted basis IDs')
        text, basis = inference['text'], inference['record_ids']
        if (not isinstance(text, str) or not text.strip() or len(text) > 600
                or not isinstance(basis, list) or not 1 <= len(basis) <= 8
                or any(not isinstance(identity, str) or identity not in identities for identity in basis)):
            raise ValueError('Inference basis must be visible admitted records')
        normalized_inferences.append(dict(text=text, record_ids=list(dict.fromkeys(basis)), kind='model_inference'))
    references = []
    for identity in identities:
        projection = allowed[identity]
        row, detail = projection['record'], projection['detail']
        references.append(dict(id=identity, title=row['title'], category=row['category'],
            summary=row['summary'], evidence=detail.get('evidence', ''), date=row.get('date', ''),
            kind=row.get('kind', 'inference'), historical=projection['historical'],
            user_corrected=detail.get('user_corrected') is True, conflict=bool(detail.get('conflict')),
            verified=detail.get('verified') is True, source_scope=detail.get('source_scope', 'record'),
            support_review=detail.get('support_review', ''), source_count=projection['source_count'],
            source_coverage=projection['source_coverage'], sources=copy.deepcopy(projection['sources']),
            revision=projection['revision']))
    return dict(status=status, answer=answer, answer_kind='model_interpretation',
                references=references, inferences=normalized_inferences)
