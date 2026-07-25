const LANGUAGE_ID = "perchance";
const FILE_EXTENSIONS = [".pjs", ".perchance"];

function isPerchanceDocument(document) {
  return document.languageId === LANGUAGE_ID;
}

module.exports = {
  LANGUAGE_ID,
  FILE_EXTENSIONS,
  isPerchanceDocument,
};
