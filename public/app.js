const form = document.getElementById('form');
const usernameInput = document.getElementById('username');
const submitBtn = document.getElementById('submit-btn');
const inputSection = document.getElementById('input-section');
const loadingSection = document.getElementById('loading-section');
const loadingMessage = document.getElementById('loading-message');
const resultsSection = document.getElementById('results-section');
const summary = document.getElementById('summary');
const booksContainer = document.getElementById('books');
const errorSection = document.getElementById('error-section');
const errorMessage = document.getElementById('error-message');
const resetBtn = document.getElementById('reset-btn');
const errorResetBtn = document.getElementById('error-reset-btn');

const LOADING_MESSAGES = [
  'Fetching your films...',
  'Analyzing your taste...',
  'Finding the perfect books...',
  'Almost there...',
];

let loadingInterval = null;

function showSection(section) {
  [inputSection, loadingSection, resultsSection, errorSection].forEach(s =>
    s.classList.add('hidden')
  );
  section.classList.remove('hidden');
}

function startLoadingMessages() {
  let i = 0;
  loadingMessage.textContent = LOADING_MESSAGES[0];
  loadingInterval = setInterval(() => {
    i = Math.min(i + 1, LOADING_MESSAGES.length - 1);
    loadingMessage.textContent = LOADING_MESSAGES[i];
  }, 4000);
}

function stopLoadingMessages() {
  clearInterval(loadingInterval);
  loadingInterval = null;
}

function renderBooks(data) {
  summary.textContent = `Based on ${data.film_count} highly-rated films from @${data.username}`;
  booksContainer.innerHTML = '';

  for (const category of data.categories) {
    const section = document.createElement('div');
    section.className = 'category-section';

    const heading = document.createElement('h2');
    heading.className = 'category-heading';
    heading.textContent = category.name;
    section.appendChild(heading);

    for (const book of category.books) {
      const card = document.createElement('div');
      card.className = 'book-card' + (book.top_pick ? ' top-pick' : '');

      const tags = book.related_films
        .map(f => `<span class="film-tag">${f}</span>`)
        .join('');

      const badge = book.top_pick ? '<span class="top-pick-badge">Top Pick</span>' : '';

      card.innerHTML = `
        <div class="book-title"><a href="${book.link}" target="_blank" rel="noopener">${book.title}</a>${badge}</div>
        <div class="book-author">by ${book.author}</div>
        <div class="book-description">${book.description}</div>
        <div class="related-films">${tags}</div>
      `;
      section.appendChild(card);
    }

    booksContainer.appendChild(section);
  }
}

function reset() {
  showSection(inputSection);
  usernameInput.value = '';
  usernameInput.focus();
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = usernameInput.value.trim();
  if (!username) return;

  showSection(loadingSection);
  startLoadingMessages();
  submitBtn.disabled = true;

  try {
    const res = await fetch('/api/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || 'Something went wrong');
    }

    renderBooks(data);
    showSection(resultsSection);
  } catch (err) {
    errorMessage.textContent = err.message;
    showSection(errorSection);
  } finally {
    stopLoadingMessages();
    submitBtn.disabled = false;
  }
});

resetBtn.addEventListener('click', reset);
errorResetBtn.addEventListener('click', reset);
