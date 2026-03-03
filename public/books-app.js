const form = document.getElementById('form');
const userIdInput = document.getElementById('user-id');
const submitBtn = document.getElementById('submit-btn');
const inputSection = document.getElementById('input-section');
const loadingSection = document.getElementById('loading-section');
const loadingMessage = document.getElementById('loading-message');
const resultsSection = document.getElementById('results-section');
const summary = document.getElementById('summary');
const filmsContainer = document.getElementById('films');
const errorSection = document.getElementById('error-section');
const errorMessage = document.getElementById('error-message');
const resetBtn = document.getElementById('reset-btn');
const errorResetBtn = document.getElementById('error-reset-btn');

const LOADING_MESSAGES = [
  'Fetching your books...',
  'Analyzing your reading taste...',
  'Finding the perfect films...',
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

function renderFilms(data) {
  summary.textContent = `Based on ${data.book_count} books from your Goodreads shelf`;
  filmsContainer.innerHTML = '';

  for (const category of data.categories) {
    const section = document.createElement('div');
    section.className = 'category-section';

    const heading = document.createElement('h2');
    heading.className = 'category-heading';
    heading.textContent = category.name;
    section.appendChild(heading);

    for (const film of category.films) {
      const card = document.createElement('div');
      card.className = 'film-card' + (film.top_pick ? ' top-pick' : '');

      const tags = film.related_books
        .map(b => `<span class="book-tag">${b}</span>`)
        .join('');

      const badge = film.top_pick ? '<span class="top-pick-badge">Top Pick</span>' : '';

      card.innerHTML = `
        <div class="film-title"><a href="${film.link}" target="_blank" rel="noopener">${film.title}</a>${badge}</div>
        <div class="film-meta">dir. ${film.director} (${film.year})</div>
        <div class="film-description">${film.description}</div>
        <div class="related-books">${tags}</div>
      `;
      section.appendChild(card);
    }

    filmsContainer.appendChild(section);
  }
}

function reset() {
  showSection(inputSection);
  userIdInput.value = '';
  userIdInput.focus();
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const userId = userIdInput.value.trim();
  if (!userId) return;

  showSection(loadingSection);
  startLoadingMessages();
  submitBtn.disabled = true;

  try {
    const res = await fetch('/api/books-recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || 'Something went wrong');
    }

    renderFilms(data);
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
