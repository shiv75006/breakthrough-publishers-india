/**
 * Date utility functions for consistent IST timezone handling
 * IST (Indian Standard Time) is UTC+5:30
 */

const IST_TIMEZONE = 'Asia/Kolkata';
const IST_LOCALE = 'en-IN';

/**
 * Parse a date string and ensure it's treated as UTC if no timezone info
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {Date} - Date object
 */
const parseDate = (dateStr) => {
  if (!dateStr) return null;
  if (dateStr instanceof Date) return dateStr;
  
  // If the date string doesn't have timezone info, treat it as UTC
  const str = String(dateStr);
  if (!str.includes('Z') && !str.includes('+') && !str.includes('-', 10)) {
    // Append 'Z' to treat as UTC
    return new Date(str + 'Z');
  }
  return new Date(str);
};

/**
 * Format date to IST date only (e.g., "25 Feb 2026")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted date string
 */
export const formatDateIST = (dateStr) => {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return 'N/A';
  
  return date.toLocaleDateString(IST_LOCALE, {
    timeZone: IST_TIMEZONE,
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  });
};

/**
 * Format date to IST time only (e.g., "2:30 PM")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted time string
 */
export const formatTimeIST = (dateStr) => {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return '';
  
  return date.toLocaleTimeString(IST_LOCALE, {
    timeZone: IST_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  });
};

/**
 * Format date to IST date and time (e.g., "25 Feb 2026, 2:30 PM")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted date and time string
 */
export const formatDateTimeIST = (dateStr) => {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return 'N/A';
  
  return date.toLocaleString(IST_LOCALE, {
    timeZone: IST_TIMEZONE,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  });
};

/**
 * Format date for US locale but in IST timezone (e.g., "Feb 25, 2026")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted date string
 */
export const formatDateUS = (dateStr) => {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return 'N/A';
  
  return date.toLocaleDateString('en-US', {
    timeZone: IST_TIMEZONE,
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
};

/**
 * Format date with full weekday (e.g., "Monday, Feb 25, 2026")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted date string with weekday
 */
export const formatDateWithWeekday = (dateStr) => {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return 'N/A';
  
  return date.toLocaleDateString('en-US', {
    timeZone: IST_TIMEZONE,
    weekday: 'long',
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
};

/**
 * Get relative date string (Today, Yesterday, or formatted date)
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Relative date string
 */
export const formatRelativeDate = (dateStr) => {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return '';
  
  // Get current date in IST
  const now = new Date();
  const nowIST = new Date(now.toLocaleString('en-US', { timeZone: IST_TIMEZONE }));
  const dateIST = new Date(date.toLocaleString('en-US', { timeZone: IST_TIMEZONE }));
  
  // Reset to start of day for comparison
  const today = new Date(nowIST.getFullYear(), nowIST.getMonth(), nowIST.getDate());
  const compareDate = new Date(dateIST.getFullYear(), dateIST.getMonth(), dateIST.getDate());
  
  const diffDays = Math.floor((today - compareDate) / (1000 * 60 * 60 * 24));
  
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  
  return formatDateUS(dateStr);
};

/**
 * Format date for short display (e.g., "25/02/2026")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Short formatted date string
 */
export const formatDateShort = (dateStr) => {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return 'N/A';
  
  return date.toLocaleDateString(IST_LOCALE, {
    timeZone: IST_TIMEZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  });
};

/**
 * Convert a date to IST Date object
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {Date} - Date object adjusted for IST display
 */
export const toISTDate = (dateStr) => {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return null;
  return date;
};

/**
 * Get future date in IST
 * @param {number} days - Number of days to add
 * @returns {Date} - Future date
 */
export const getFutureDate = (days) => {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date;
};

/**
 * Format future date with weekday
 * @param {number} days - Number of days from now
 * @returns {string} - Formatted future date string
 */
export const formatFutureDateWithWeekday = (days) => {
  const futureDate = getFutureDate(days);
  return formatDateWithWeekday(futureDate);
};

export default {
  formatDateIST,
  formatTimeIST,
  formatDateTimeIST,
  formatDateUS,
  formatDateWithWeekday,
  formatRelativeDate,
  formatDateShort,
  toISTDate,
  getFutureDate,
  formatFutureDateWithWeekday
};
