import React from 'react';
import { useNavigate } from 'react-router-dom';
import StatusChips from '../StatusChips/StatusChips';
import styles from './PaperCard.module.css';

/**
 * Reusable Paper Card component for displaying paper information
 * @param {Object} paper - Paper data object
 * @param {String} actions - Action type: 'admin', 'editor', 'author', 'minimal'
 * @param {Function} onManage - Callback when manage button is clicked
 * @param {Function} onView - Callback when view button is clicked
 * @param {String} role - Current user role for filtering available actions
 */
const PaperCard = ({ paper, actions = 'minimal', onManage, onView, role }) => {
  const navigate = useNavigate();

  if (!paper) return null;

  const title = paper.title || paper.name || 'Untitled Paper';
  const date = paper.added_on ? new Date(paper.added_on).toLocaleDateString() : 'N/A';

  const handleManage = () => {
    // Navigate to details page for admin/editor, use callback for others
    if (actions === 'admin' || actions === 'editor') {
      const routes = {
        admin: `/admin/submissions/${paper.id}`,
        editor: `/editor/papers/${paper.id}`,
      };
      navigate(routes[actions]);
    } else if (onManage) {
      onManage(paper.id);
    }
  };

  const handleView = () => {
    if (onView) {
      onView(paper.id);
    } else {
      // Default navigate based on role
      const routes = {
        admin: `/admin/submissions/${paper.id}`,
        editor: `/editor/papers/${paper.id}`,
        author: `/author/submissions/${paper.id}`,
        reviewer: `/reviewer/assignments/${paper.id}`,
      };
      const route = routes[role] || `/paper/${paper.id}`;
      navigate(route);
    }
  };

  return (
    <div className={styles.paperCard}>
      <div className={styles.cardContent}>
        <div className={styles.titleSection}>
          <h3 className={styles.title}>{title}</h3>
        </div>

        <div className={styles.metaSection}>
          <div className={styles.metaLeft}>
            <span className={styles.metaItem}>
              <span className="material-symbols-rounded">calendar_today</span>
              {date}
            </span>
            <StatusChips status={paper.status} />
            {paper.journal_name && (
              <span className={styles.metaItem}>
                <span className="material-symbols-rounded">book</span>
                {paper.journal_name}
              </span>
            )}
            {/* Review Status Chip for Admin/Editor */}
            {(actions === 'admin' || actions === 'editor') && paper.review_status && (
              <span className={`${styles.reviewStatusChip} ${styles[`review_${paper.review_status}`]}`}>
                <span className="material-symbols-rounded">
                  {paper.review_status === 'reviewed' ? 'check_circle' : 
                   paper.review_status === 'partial' ? 'pending' :
                   paper.review_status === 'pending' ? 'hourglass_empty' : 'person_add'}
                </span>
                {paper.review_status === 'not_assigned' ? 'Not Assigned' :
                 paper.review_status === 'pending' ? 'Review Pending' :
                 paper.review_status === 'partial' ? `Reviewed ${paper.completed_reviews}/${paper.total_reviewers}` :
                 `Reviewed ${paper.completed_reviews}/${paper.total_reviewers}`}
              </span>
            )}
          </div>

          <div className={styles.metaRight}>
          </div>
        </div>
      </div>

      {/* Admin Actions: MANAGE button */}
      {(actions === 'admin' || actions === 'editor') && (
        <button
          className={`${styles.actionBtn} ${styles.manageBtn}`}
          onClick={handleManage}
        >
          <span>Manage</span>
          <span className="material-symbols-rounded">chevron_right</span>
        </button>
      )}

      {/* Author Actions: VIEW ONLY */}
      {actions === 'author' && (
        <button
          className={`${styles.actionBtn} ${styles.viewOnlyBtn}`}
          onClick={handleView}
        >
          <span>VIEW</span>
          <span className="material-symbols-rounded">open_in_new</span>
        </button>
      )}

      {/* Reviewer Actions: REVIEW button */}
      {actions === 'reviewer' && (
        <button
          className={`${styles.actionBtn} ${styles.reviewBtn}`}
          onClick={handleManage}
        >
          <span>REVIEW</span>
          <span className="material-symbols-rounded">edit_note</span>
        </button>
      )}
    </div>
  );
};

export default PaperCard;
