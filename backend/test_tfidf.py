"""Test Journal Recommendation Service"""
from app.db.database import SessionLocal
from app.services.journal_recommendation_service import JournalRecommendationService
from app.db.models import Journal, JournalDetails

db = SessionLocal()
service = JournalRecommendationService(db)

# Test 1: Humanities abstract
print("=== Test 1: Humanities Abstract ===")
kw1 = ['sociology', 'cultural studies', 'social behavior', 'humanities', 'society']
abs1 = 'This paper examines the social and cultural dynamics of urban communities. We analyze behavioral patterns and cultural practices that shape social interactions in diverse communities and societies.'
results1 = service.get_recommendations(kw1, abs1)
print(f'Results: {len(results1)}')
for r in results1:
    print(f'  {r["journal_name"]}: {r["score"]} - {r["match_reason"]}')

# Test 2: Operations Research abstract
print("\n=== Test 2: Operations Abstract ===")
kw2 = ['optimization', 'operations research', 'supply chain', 'inventory', 'management']
abs2 = 'This paper proposes a mathematical programming approach to supply chain optimization. We develop algorithms for inventory management and logistics operations in manufacturing systems.'
results2 = service.get_recommendations(kw2, abs2)
print(f'Results: {len(results2)}')
for r in results2:
    print(f'  {r["journal_name"]}: {r["score"]} - {r["match_reason"]}')

# List all journals
print("\n=== Available Journals ===")
journals = db.query(Journal).all()
for j in journals[:15]:
    print(f'  - {j.fld_journal_name}')
if len(journals) > 15:
    print(f'  ... and {len(journals) - 15} more')

# Debug: Show scores for first journal
print("\n=== Debug Scores (first journal) ===")
j = journals[0]
details_map = {}
for d in db.query(JournalDetails).all():
    details_map[str(d.journal_id)] = d
details = details_map.get(str(j.fld_id))
jtext = service._build_journal_text(j, details)
print(f'Journal: {j.fld_journal_name}')
print(f'Text length: {len(jtext)}')
abs_score = service._compute_tfidf_similarity(abs1, jtext)
kw_score, matched = service._compute_keyword_overlap(kw1, jtext)
print(f'Abstract score: {abs_score}')
print(f'Keyword score: {kw_score}')
print(f'Matched keywords: {matched}')
print(f'Final: {abs_score * 0.7 + kw_score * 0.3}')

db.close()
