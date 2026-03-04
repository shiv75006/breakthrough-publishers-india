"""
Journal Recommendation Service for Authors

Uses category-based filtering combined with NLP similarity matching:
1. Category Filter (HARD): Only journals in the selected research area
2. Abstract matching: Paper abstract vs Journal scope/description using TF-IDF
3. Keyword matching: Author keywords vs Journal content

This ensures authors only see journals in their discipline.
"""

import logging
import re
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.db.models import Journal, JournalDetails

logger = logging.getLogger(__name__)


class JournalRecommendationService:
    """Service for computing journal recommendations based on research area, abstract and keywords."""
    
    # Weight configuration for scoring within a category
    ABSTRACT_WEIGHT = 0.6  # Weight for abstract match
    KEYWORD_WEIGHT = 0.4   # Weight for keyword match
    
    # Threshold for recommendations (within category)
    MIN_RECOMMENDATION_SCORE = 0.05
    
    # Maximum recommendations to return
    MAX_RECOMMENDATIONS = 3
    
    def __init__(self, db: Session):
        self.db = db
    
    def _clean_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        if not text:
            return ""
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
    
    def _build_journal_text(self, journal: Journal, details: JournalDetails = None) -> str:
        """Combine journal fields into searchable text."""
        parts = []
        
        if journal.fld_journal_name:
            parts.append(journal.fld_journal_name)
        
        if journal.description:
            parts.append(self._clean_html(journal.description))
        
        if details:
            if details.scope:
                scope_text = self._clean_html(details.scope)
                parts.append(scope_text)
                parts.append(scope_text)  # Double weight for scope
            
            if details.aim_objective:
                parts.append(self._clean_html(details.aim_objective))
            
            if details.about_journal:
                parts.append(self._clean_html(details.about_journal))
        
        return ' '.join(parts).lower().strip()
    
    def _compute_tfidf_similarity(self, text1: str, text2: str) -> float:
        """
        Compute TF-IDF based cosine similarity between two texts.
        """
        if not text1 or not text2:
            return 0.0
        
        text1 = text1.lower().strip()
        text2 = text2.lower().strip()
        
        if len(text1) < 20 or len(text2) < 20:
            return 0.0
        
        try:
            vectorizer = TfidfVectorizer(
                lowercase=True,
                stop_words='english',
                ngram_range=(1, 2),
                max_features=2000,
                min_df=1,
                max_df=0.95,
            )
            
            tfidf_matrix = vectorizer.fit_transform([text1, text2])
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            
            # Fallback to word overlap if TF-IDF returns 0
            if similarity < 0.01:
                words1 = set(re.findall(r'\b[a-z]{4,}\b', text1))
                words2 = set(re.findall(r'\b[a-z]{4,}\b', text2))
                common = words1 & words2
                if common:
                    similarity = len(common) / min(len(words1), len(words2), 50)
                    similarity = min(similarity, 0.3)
            
            return float(similarity)
            
        except Exception as e:
            logger.warning(f"Error computing TF-IDF similarity: {e}")
            return 0.0
    
    def _compute_keyword_overlap(self, keywords: List[str], journal_text: str) -> Tuple[float, List[str]]:
        """
        Compute keyword overlap score.
        """
        if not keywords or not journal_text:
            return 0.0, []
        
        journal_text_lower = journal_text.lower()
        journal_words = set(re.findall(r'\b[a-z]{3,}\b', journal_text_lower))
        
        matched_keywords = []
        match_score = 0.0
        
        for kw in keywords:
            kw_lower = kw.lower().strip()
            kw_words = set(re.findall(r'\b[a-z]{3,}\b', kw_lower))
            
            if kw_lower in journal_text_lower:
                matched_keywords.append(kw)
                match_score += 1.0
            elif kw_words & journal_words:
                matched_keywords.append(kw)
                match_score += 0.5
        
        if len(keywords) > 0:
            match_score = match_score / len(keywords)
        
        return min(match_score, 1.0), list(set(matched_keywords))
    
    def _generate_match_reason(self, matched_keywords: List[str], abstract_score: float, category: str) -> str:
        """Generate a human-readable reason for the recommendation."""
        if abstract_score > 0.3:
            return f"Strong match in {category}"
        elif abstract_score > 0.15:
            return f"Good scope alignment"
        elif matched_keywords:
            kw_str = ', '.join(matched_keywords[:3])
            if len(matched_keywords) > 3:
                kw_str += f" +{len(matched_keywords) - 3} more"
            return f"Keywords: {kw_str}"
        else:
            return f"Relevant in {category}"
    
    def compute_journal_score(
        self,
        keywords: List[str],
        abstract: str,
        journal: Journal,
        details: JournalDetails = None
    ) -> Dict:
        """
        Compute recommendation score for a journal.
        """
        journal_text = self._build_journal_text(journal, details)
        
        if not journal_text:
            return {
                "journal_id": journal.fld_id,
                "journal_name": journal.fld_journal_name,
                "score": 0.0,
                "is_recommended": False,
                "match_reason": ""
            }
        
        # Compute abstract similarity using TF-IDF
        abstract_score = 0.0
        if abstract and len(abstract.strip()) >= 50:
            abstract_score = self._compute_tfidf_similarity(abstract, journal_text)
            abstract_score = min(abstract_score * 1.2, 1.0)
        
        # Compute keyword overlap
        keyword_score, matched_keywords = self._compute_keyword_overlap(keywords, journal_text)
        
        # Combine scores
        final_score = (abstract_score * self.ABSTRACT_WEIGHT) + (keyword_score * self.KEYWORD_WEIGHT)
        
        # Determine if recommended
        is_recommended = final_score >= self.MIN_RECOMMENDATION_SCORE
        
        # Generate reason
        match_reason = ""
        if is_recommended:
            category = journal.fld_primary_category or "your field"
            match_reason = self._generate_match_reason(matched_keywords, abstract_score, category)
        
        return {
            "journal_id": journal.fld_id,
            "journal_name": journal.fld_journal_name,
            "score": round(final_score, 3),
            "is_recommended": is_recommended,
            "match_reason": match_reason
        }
    
    def get_recommendations(
        self,
        research_area: str,
        keywords: List[str],
        abstract: str = ""
    ) -> List[Dict]:
        """
        Get journal recommendations for given research area, keywords and abstract.
        
        Uses HARD FILTER by research_area - only journals in the same category are considered.
        Within the category, scoring is based on abstract (60%) + keywords (40%).
        
        Args:
            research_area: The research category (required for filtering)
            keywords: List of keywords from the paper
            abstract: Paper abstract (optional but improves accuracy)
        
        Returns:
            List of recommended journals with scores and reasons
        """
        if not research_area:
            logger.warning("No research area provided, cannot filter journals")
            return []
        
        # HARD FILTER: Get only journals in the selected research area
        journals = self.db.query(Journal).filter(
            Journal.fld_primary_category == research_area
        ).all()
        
        if not journals:
            logger.info(f"No journals found in category: {research_area}")
            return []
        
        # Get all journal details
        details_map = {}
        all_details = self.db.query(JournalDetails).all()
        for d in all_details:
            details_map[str(d.journal_id)] = d
        
        # Compute scores for journals in the category
        scored_journals = []
        for journal in journals:
            details = details_map.get(str(journal.fld_id))
            score_result = self.compute_journal_score(keywords, abstract, journal, details)
            
            # All journals in the category are "recommended" since they passed the filter
            score_result["is_recommended"] = True
            if not score_result["match_reason"]:
                score_result["match_reason"] = f"In {research_area}"
            scored_journals.append(score_result)
        
        # Sort by score descending
        scored_journals.sort(key=lambda x: x["score"], reverse=True)
        
        # Return top N recommendations
        return scored_journals[:self.MAX_RECOMMENDATIONS]
