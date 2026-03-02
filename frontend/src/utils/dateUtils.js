/**
 * Date utility functions for consistent IST timezone handling
 * IST (Indian Standard Time) is UTC+5:30
 */

const IST_TIMEZONE = 'Asia/Kolkata';
const IST_LOCALE = 'en-IN';
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000; // 5 hours 30 minutes in milliseconds

/**
 * Parse a date string and ensure it's treated as UTC if no timezone info.
 * Backend sends dates like "2026-03-02T08:12:16" which are in UTC but without 'Z'.
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {Date} - Date object in UTC
 */
const parseDate = (dateStr) => {
  if (!dateStr) return null;
  if (dateStr instanceof Date) return dateStr;
  
  let str = String(dateStr).trim();
  
  // Check if already has timezone info (Z, +HH:MM, -HH:MM)
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$|[+-]\d{4}$/.test(str);
  
  if (!hasTimezone) {
    // Replace space with 'T' for ISO compatibility
    str = str.replace(' ', 'T');
    // Append 'Z' to interpret as UTC
    if (!str.endsWith('Z')) {
      str = str + 'Z';
    }
  }
  
  const date = new Date(str);
  return isNaN(date.getTime()) ? null : date;
};

/**
 * Convert UTC Date to IST Date by adding 5:30 offset.
 * This is a manual conversion that doesn't rely on browser timezone DB.
 * @param {Date} utcDate - Date in UTC
 * @returns {Date} - Date shifted to IST (for display purposes)
 */
const toISTManual = (utcDate) => {
  if (!utcDate || isNaN(utcDate.getTime())) return null;
  return new Date(utcDate.getTime() + IST_OFFSET_MS);
};

/**
 * Format a date component with leading zero
 */
const pad = (num) => String(num).padStart(2, '0');

/**
 * Get month short name
 */
const getMonthShort = (monthIndex) => {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return months[monthIndex];
};

/**
 * Get weekday name
 */
const getWeekday = (dayIndex) => {
  const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  return days[dayIndex];
};

/**
 * Format 24h to 12h with AM/PM
 */
const formatTime12h = (hours, minutes) => {
  const period = hours >= 12 ? 'pm' : 'am';
  const hours12 = hours % 12 || 12;
  return `${hours12}:${pad(minutes)} ${period}`;
};

/**
 * Format date to IST date only (e.g., "2 Mar 2026")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted date string
 */
export const formatDateIST = (dateStr) => {
  const utcDate = parseDate(dateStr);
  if (!utcDate) return 'N/A';
  
  const istDate = toISTManual(utcDate);
  const day = istDate.getUTCDate();
  const month = getMonthShort(istDate.getUTCMonth());
  const year = istDate.getUTCFullYear();
  
  return `${day} ${month} ${year}`;
};

/**
 * Format date to IST time only (e.g., "2:30 pm")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted time string
 */
export const formatTimeIST = (dateStr) => {
  const utcDate = parseDate(dateStr);
  if (!utcDate) return '';
  
  const istDate = toISTManual(utcDate);
  return formatTime12h(istDate.getUTCHours(), istDate.getUTCMinutes());
};

/**
 * Format date to IST date and time (e.g., "2 Mar 2026, 2:30 pm")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted date and time string
 */
export const formatDateTimeIST = (dateStr) => {
  const utcDate = parseDate(dateStr);
  if (!utcDate) return 'N/A';
  
  const istDate = toISTManual(utcDate);
  const day = istDate.getUTCDate();
  const month = getMonthShort(istDate.getUTCMonth());
  const year = istDate.getUTCFullYear();
  const time = formatTime12h(istDate.getUTCHours(), istDate.getUTCMinutes());
  
  return `${day} ${month} ${year}, ${time}`;
};

/**
 * Format date for US locale but in IST timezone (e.g., "Feb 25, 2026")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted date string
 */
export const formatDateUS = (dateStr) => {
  const utcDate = parseDate(dateStr);
  if (!utcDate) return 'N/A';
  
  const istDate = toISTManual(utcDate);
  const month = getMonthShort(istDate.getUTCMonth());
  const day = istDate.getUTCDate();
  const year = istDate.getUTCFullYear();
  
  return `${month} ${day}, ${year}`;
};

/**
 * Format date with full weekday (e.g., "Monday, Feb 25, 2026")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Formatted date string with weekday
 */
export const formatDateWithWeekday = (dateStr) => {
  const utcDate = parseDate(dateStr);
  if (!utcDate) return 'N/A';
  
  const istDate = toISTManual(utcDate);
  const weekday = getWeekday(istDate.getUTCDay());
  const month = getMonthShort(istDate.getUTCMonth());
  const day = istDate.getUTCDate();
  const year = istDate.getUTCFullYear();
  
  return `${weekday}, ${month} ${day}, ${year}`;
};

/**
 * Get relative date string (Today, Yesterday, or formatted date)
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Relative date string
 */
export const formatRelativeDate = (dateStr) => {
  const utcDate = parseDate(dateStr);
  if (!utcDate) return '';
  
  // Get current time in IST
  const nowIST = toISTManual(new Date());
  const dateIST = toISTManual(utcDate);
  
  // Compare dates (day only)
  const todayStart = new Date(Date.UTC(nowIST.getUTCFullYear(), nowIST.getUTCMonth(), nowIST.getUTCDate()));
  const dateStart = new Date(Date.UTC(dateIST.getUTCFullYear(), dateIST.getUTCMonth(), dateIST.getUTCDate()));
  
  const diffDays = Math.floor((todayStart - dateStart) / (1000 * 60 * 60 * 24));
  
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  
  return formatDateUS(dateStr);
};

/**
 * Format date for short display (e.g., "02/03/2026")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} - Short formatted date string
 */
export const formatDateShort = (dateStr) => {
  const utcDate = parseDate(dateStr);
  if (!utcDate) return 'N/A';
  
  const istDate = toISTManual(utcDate);
  const day = pad(istDate.getUTCDate());
  const month = pad(istDate.getUTCMonth() + 1);
  const year = istDate.getUTCFullYear();
  
  return `${day}/${month}/${year}`;
};

/**
 * Convert a date to IST Date object
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {Date} - Date object adjusted for IST display
 */
export const toISTDate = (dateStr) => {
  const utcDate = parseDate(dateStr);
  if (!utcDate) return null;
  return toISTManual(utcDate);
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
