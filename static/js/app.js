const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const ui = {
  menuButton: $('#menuButton'), closeDrawerButton: $('#closeDrawerButton'), drawer: $('#drawer'), drawerBackdrop: $('#drawerBackdrop'),
  settingsButton: $('#settingsButton'), settingsModal: $('#settingsModal'), identifyModal: $('#identifyModal'),
  driveSelect: $('#driveSelect'), scanButton: $('#scanButton'), ejectButton: $('#ejectButton'), statusDot: $('#statusDot'), deviceStatus: $('#deviceStatus'),
  discShell: $('#discShell'), coverImage: $('#coverImage'), trackChipText: $('#trackChipText'), trackTitle: $('#trackTitle'), artistName: $('#artistName'), albumName: $('#albumName'), equalizer: $('#equalizer'),
  progressRange: $('#progressRange'), elapsedTime: $('#elapsedTime'), remainingTime: $('#remainingTime'), playButton: $('#playButton'), playIcon: $('#playIcon'), previousButton: $('#previousButton'), nextButton: $('#nextButton'), shuffleButton: $('#shuffleButton'), repeatButton: $('#repeatButton'), repeatLabel: $('#repeatLabel'), lyricsQuickButton: $('#lyricsQuickButton'), volumeRange: $('#volumeRange'), volumeKnob: $('#volumeKnob'),
  tracksAlbumTitle: $('#tracksAlbumTitle'), trackCount: $('#trackCount'), trackList: $('#trackList'),
  lyricsTitle: $('#lyricsTitle'), lyricsContent: $('#lyricsContent'),
  artistImage: $('#artistImage'), artistPanelName: $('#artistPanelName'), artistTags: $('#artistTags'), artistBiography: $('#artistBiography'), artistSource: $('#artistSource'), discographyGrid: $('#discographyGrid'),
  identifyBanner: $('#identifyBanner'), identifyDiagnostic: $('#identifyDiagnostic'), identifyButton: $('#identifyButton'), releaseSearchForm: $('#releaseSearchForm'), releaseSearchInput: $('#releaseSearchInput'), releaseResults: $('#releaseResults'), manualArtist: $('#manualArtist'), manualAlbum: $('#manualAlbum'), manualTrackTitles: $('#manualTrackTitles'), retryAutomaticButton: $('#retryAutomaticButton'), saveManualButton: $('#saveManualButton'),
  musicbrainzContact: $('#musicbrainzContact'), autoLyricsToggle: $('#autoLyricsToggle'), saveSettingsButton: $('#saveSettingsButton'), clearCacheButton: $('#clearCacheButton'), clearCollectionButton: $('#clearCollectionButton'),
  collectionGallery: $('#collectionGallery'), collectionSearch: $('#collectionSearch'), collectionSort: $('#collectionSort'), collectionCount: $('#collectionCount'), collectionUpdated: $('#collectionUpdated'), statAlbums: $('#statAlbums'), statArtists: $('#statArtists'), statPlays: $('#statPlays'), statTime: $('#statTime'), favoriteGenre: $('#favoriteGenre'), genreBars: $('#genreBars'), topArtists: $('#topArtists'),
  toast: $('#toast'), playerCard: $('.player-card'), vuDeck: $('#vuDeck'),
};

const state = {
  disc: null, server: null, player: { mode: 'stopped', track: 1, position: 0, duration: 0 },
  currentTrack: 1, revision: -1, shuffle: false, repeat: 'off', seeking: false,
  lyricLines: [],
  settings: { auto_lyrics: true, default_volume: 80 },
  collection: { albums: [], summary: {}, genres: [], top_artists: [] },
};

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  let payload = {};
  try { payload = await response.json(); } catch (_) { /* sem JSON */ }
  if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.message || `Erro HTTP ${response.status}`);
  return payload;
}

function escapeHtml(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

function formatTime(value) {
  const total = Math.max(0, Math.floor(Number(value) || 0));
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}

let toastTimer;
function showToast(message, timeout = 4200) {
  clearTimeout(toastTimer);
  ui.toast.textContent = String(message || '');
  ui.toast.classList.add('visible');
  toastTimer = setTimeout(() => ui.toast.classList.remove('visible'), timeout);
}

function openModal(element) {
  element.classList.remove('closing');
  element.classList.add('open');
  element.setAttribute('aria-hidden', 'false');
}
function closeModal(element) {
  element.classList.add('closing');
  element.setAttribute('aria-hidden', 'true');
  setTimeout(() => { element.classList.remove('open', 'closing'); }, 240);
}

function retriggerAnimation(element, className, timeout = 520) {
  if (!element) return;
  element.classList.remove(className);
  void element.offsetWidth;
  element.classList.add(className);
  setTimeout(() => element.classList.remove(className), timeout);
}

function animateTrackChange() {
  retriggerAnimation(ui.playerCard, 'track-switching', 620);
  retriggerAnimation(ui.trackTitle, 'title-switching', 520);
}

function createButtonRipple(event) {
  const button = event.currentTarget;
  const bounds = button.getBoundingClientRect();
  const ripple = document.createElement('span');
  ripple.className = 'button-ripple';
  ripple.style.left = `${event.clientX - bounds.left}px`;
  ripple.style.top = `${event.clientY - bounds.top}px`;
  button.appendChild(ripple);
  setTimeout(() => ripple.remove(), 620);
}
function setPanel(panelId) {
  $$('.panel-view').forEach((panel) => {
    const willBeActive = panel.id === panelId;
    panel.classList.toggle('active', willBeActive);
    if (willBeActive) retriggerAnimation(panel, 'panel-entering', 520);
  });
  $$('.panel-tab').forEach((button) => button.classList.toggle('active', button.dataset.panel === panelId));
  if (panelId === 'collectionPanel') loadCollection();
  if (window.innerWidth <= 900) $('#contentPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function currentTrackData() {
  return state.disc?.tracks?.[state.currentTrack - 1] || null;
}

function setStatus(kind, message) {
  ui.statusDot.className = `status-dot ${kind || ''}`.trim();
  ui.deviceStatus.textContent = message;
}

function renderDriveState(serverState) {
  const drives = serverState.drives || [];
  const selected = serverState.selected_drive || '';
  ui.driveSelect.innerHTML = drives.length ? drives.map((drive) => `<option value="${drive}">${drive}</option>`).join('') : '<option value="">Sem leitor</option>';
  ui.driveSelect.value = selected;

  if (!drives.length) setStatus('error', 'Nenhum leitor de CD/DVD encontrado');
  else if (serverState.metadata_loading) setStatus('loading', 'Procurando álbum, músicas e artista…');
  else if (serverState.disc) setStatus('ready', `CD pronto em ${selected}`);
  else setStatus('', `Insira um CD em ${selected}`);
  if (serverState.error) showToast(serverState.error);
}

function renderDisc(disc) {
  state.disc = disc;
  if (!disc) {
    state.currentTrack = 1;
    ui.coverImage.src = '/static/img/disc-placeholder.svg';
    ui.trackTitle.textContent = 'Insira um CD de áudio';
    ui.artistName.textContent = 'O AuraCD procurará as informações automaticamente';
    ui.albumName.textContent = '—';
    ui.trackChipText.textContent = 'Aguardando CD';
    ui.tracksAlbumTitle.textContent = 'Nenhum disco carregado';
    ui.trackCount.textContent = '0 faixas';
    ui.trackList.innerHTML = '<div class="empty-state"><div class="empty-disc">●</div><p>Insira um CD para ver as músicas.</p></div>';
    ui.identifyBanner.classList.remove('visible');
    renderArtist(null);
    renderLyricsEmpty('A letra aparecerá aqui quando uma faixa identificada for selecionada.');
    return;
  }

  if (state.currentTrack > disc.tracks.length) state.currentTrack = 1;
  ui.coverImage.src = disc.cover_url || '/static/img/disc-placeholder.svg';
  ui.tracksAlbumTitle.textContent = disc.album || 'CD de áudio';
  ui.trackCount.textContent = `${disc.tracks.length} ${disc.tracks.length === 1 ? 'faixa' : 'faixas'}`;
  const needsManual = Boolean(disc.metadata_ready && !disc.identified && disc.needs_manual_search);
  ui.identifyBanner.classList.toggle('visible', needsManual);
  ui.identifyDiagnostic.textContent = needsManual ? (disc.diagnostic || `Leitura: ${disc.reader || 'MCI'} · Disc ID: ${disc.disc_id || 'indisponível'}`) : '';
  renderTrackList();
  renderNowPlaying();
  renderArtist(disc.artist_details || null);
}

function renderNowPlaying() {
  const track = currentTrackData();
  if (!track || !state.disc) return;
  ui.trackTitle.textContent = track.title || `Faixa ${state.currentTrack}`;
  ui.artistName.textContent = track.artist || state.disc.artist || 'Artista desconhecido';
  ui.albumName.textContent = [state.disc.album, state.disc.year].filter(Boolean).join(' · ') || 'CD de áudio';
  ui.trackChipText.textContent = `Faixa ${String(state.currentTrack).padStart(2, '0')}`;
  ui.lyricsTitle.textContent = track.title || `Faixa ${state.currentTrack}`;
  $$('.track-item').forEach((item) => item.classList.toggle('active', Number(item.dataset.track) === state.currentTrack));
  animateTrackChange();
}

function renderTrackList() {
  if (!state.disc?.tracks?.length) return;
  ui.trackList.innerHTML = state.disc.tracks.map((track, index) => `
    <button class="track-item ${track.number === state.currentTrack ? 'active' : ''}" style="--item-delay:${Math.min(index * 42, 420)}ms" data-track="${track.number}" type="button">
      <span class="track-number">${String(track.number).padStart(2, '0')}</span>
      <span class="track-copy"><strong>${escapeHtml(track.title || `Faixa ${track.number}`)}</strong><small>${escapeHtml(track.artist || state.disc.artist || '')}</small></span>
      <span class="track-duration">${formatTime(track.duration)}</span>
      <span class="track-led" aria-hidden="true"></span>
    </button>`).join('');
  $$('.track-item').forEach((button) => button.addEventListener('click', () => playTrack(Number(button.dataset.track))));
}

function renderArtist(details) {
  if (!details || !state.disc?.identified) {
    ui.artistImage.src = state.disc?.cover_url || '/static/img/disc-placeholder.svg';
    ui.artistPanelName.textContent = state.disc?.artist || 'Artista';
    ui.artistBiography.textContent = state.disc ? 'Identifique o CD para carregar a biografia e a discografia.' : 'As informações aparecerão após a identificação do CD.';
    ui.artistTags.innerHTML = '';
    ui.artistSource.classList.add('hidden');
    ui.discographyGrid.innerHTML = '<p class="muted">Nenhum lançamento carregado.</p>';
    return;
  }
  ui.artistImage.src = details.image || state.disc.cover_url || '/static/img/disc-placeholder.svg';
  ui.artistPanelName.textContent = details.name || state.disc.artist || 'Artista';
  ui.artistBiography.textContent = details.biography || 'Biografia não encontrada.';
  ui.artistTags.innerHTML = (details.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join('');
  if (details.source_url) { ui.artistSource.href = details.source_url; ui.artistSource.classList.remove('hidden'); } else ui.artistSource.classList.add('hidden');
  const releases = details.discography || [];
  ui.discographyGrid.innerHTML = releases.length ? releases.map((release) => `<article class="discography-card"><strong>${escapeHtml(release.title)}</strong><small>${escapeHtml([release.type, release.date].filter(Boolean).join(' · '))}</small></article>`).join('') : '<p class="muted">Nenhum lançamento encontrado.</p>';
}

async function refreshDisc() {
  try {
    const serverState = await api('/api/disc');
    state.server = serverState;
    renderDriveState(serverState);
    if (serverState.revision !== state.revision) {
      const previousDisc = state.disc?.disc_id;
      const incomingDisc = serverState.disc || null;
      const discChanged = Boolean(incomingDisc?.disc_id && incomingDisc.disc_id !== previousDisc);
      state.revision = serverState.revision;
      if (discChanged) {
        state.currentTrack = 1;
      }
      renderDisc(incomingDisc);
      if (incomingDisc?.identified && incomingDisc?.metadata_ready) loadCollection();
    }
  } catch (_) { setStatus('error', 'Aplicativo local indisponível'); }
}

async function refreshPlayerStatus() {
  try {
    const status = await api('/api/player/status');
    state.player = status;
    if (status.track && status.track !== state.currentTrack && state.disc) {
      state.currentTrack = status.track;
      renderNowPlaying();
    }
    const playing = status.mode === 'playing';
    const paused = status.mode === 'paused';
    ui.discShell.classList.toggle('playing', playing || paused);
    ui.discShell.classList.toggle('paused', paused);
    ui.playerCard?.classList.toggle('is-playing', playing);
    ui.playerCard?.classList.toggle('is-paused', paused);
    ui.equalizer.classList.toggle('playing', playing);
    ui.vuDeck?.classList.toggle('playing', playing);
    ui.playIcon.textContent = playing ? 'Ⅱ' : '▶';
    ui.playButton.setAttribute('aria-label', playing ? 'Pausar' : 'Reproduzir');
    if (Number.isFinite(Number(status.volume))) setVolumeVisual(Number(status.volume));

    if (typeof status.shuffle === 'boolean') state.shuffle = status.shuffle;
    if (status.repeat) state.repeat = status.repeat;
    ui.shuffleButton.classList.toggle('active', state.shuffle);
    ui.repeatButton.classList.toggle('active', state.repeat !== 'off');
    ui.repeatLabel.textContent = state.repeat === 'one' ? 'REP 1' : 'REP';

    if (!state.seeking) {
      const duration = Number(status.duration || currentTrackData()?.duration || 0);
      const position = Math.min(Number(status.position || 0), duration || 0);
      ui.progressRange.max = duration || 1;
      ui.progressRange.value = position;
      ui.elapsedTime.textContent = formatTime(position);
      ui.remainingTime.textContent = formatTime(duration);
      highlightCurrentLyric(position);
    }

    // A troca automática é controlada pelo backend para continuar funcionando
    // mesmo com a aba em segundo plano.
  } catch (_) { /* estado geral cuida do aviso */ }
}

async function playTrack(number, offset = 0) {
  if (!state.disc?.tracks?.length) return showToast('Insira um CD de áudio primeiro.');
  state.currentTrack = Math.max(1, Math.min(number, state.disc.tracks.length));
  renderNowPlaying();
  try {
    await api('/api/player/play', { method: 'POST', body: JSON.stringify({ track: state.currentTrack, offset }) });
    if (state.settings.auto_lyrics) loadLyrics(state.currentTrack);
    loadCollection();
  } catch (error) { showToast(error.message); }
}

async function togglePlay() {
  if (!state.disc) return showToast('Insira um CD de áudio primeiro.');
  try {
    if (state.player.mode === 'playing') await api('/api/player/pause', { method: 'POST' });
    else if (state.player.mode === 'paused') await api('/api/player/resume', { method: 'POST' });
    else await playTrack(state.currentTrack);
  } catch (error) { showToast(error.message); }
}

function randomTrack(excluding) {
  const count = state.disc?.tracks?.length || 0;
  if (count <= 1) return 1;
  let selected = excluding;
  while (selected === excluding) selected = Math.floor(Math.random() * count) + 1;
  return selected;
}

async function previousTrack() {
  if (!state.disc) return;
  const target = state.shuffle ? randomTrack(state.currentTrack) : (state.currentTrack <= 1 ? state.disc.tracks.length : state.currentTrack - 1);
  await playTrack(target);
}

async function nextTrack() {
  if (!state.disc) return;
  const target = state.shuffle ? randomTrack(state.currentTrack) : (state.currentTrack >= state.disc.tracks.length ? 1 : state.currentTrack + 1);
  await playTrack(target);
}

function renderLyricsEmpty(message) {
  state.lyricLines = [];
  ui.lyricsContent.innerHTML = `<p class="muted">${escapeHtml(message)}</p>`;
}

function parseSyncedLyrics(value) {
  return String(value || '').split('\n').map((line) => {
    const match = line.match(/^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/);
    if (!match) return null;
    return { time: Number(match[1]) * 60 + Number(match[2]), text: match[3].trim() || '♪' };
  }).filter(Boolean);
}

async function loadLyrics(number) {
  if (!state.disc?.identified) {
    renderLyricsEmpty('Identifique o CD antes de procurar letras.');
    setPanel('lyricsPanel');
    return;
  }
  ui.lyricsContent.innerHTML = '<div class="loading-spinner"></div>';
  try {
    const result = await api(`/api/track/${number}/lyrics`);
    if (!result.found) return renderLyricsEmpty(result.message || 'Letra não encontrada.');
    if (result.instrumental) return renderLyricsEmpty('Esta faixa está marcada como instrumental.');
    state.lyricLines = parseSyncedLyrics(result.synced);
    if (state.lyricLines.length) {
      ui.lyricsContent.innerHTML = state.lyricLines.map((line, index) => `<p class="lyric-line" data-index="${index}">${escapeHtml(line.text)}</p>`).join('');
    } else {
      ui.lyricsContent.innerHTML = String(result.plain || '').split('\n').map((line) => `<p>${escapeHtml(line || ' ')}</p>`).join('');
    }
  } catch (error) { renderLyricsEmpty(error.message); }
}

function highlightCurrentLyric(position) {
  if (!state.lyricLines.length) return;
  let active = 0;
  for (let index = 0; index < state.lyricLines.length; index += 1) {
    if (state.lyricLines[index].time <= position) active = index; else break;
  }
  $$('.lyric-line').forEach((line, index) => line.classList.toggle('active', index === active));
  const element = $(`.lyric-line[data-index="${active}"]`);
  if (element) element.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

function populateManualTrackTitles() {
  const tracks = state.disc?.tracks || [];
  ui.manualTrackTitles.innerHTML = tracks.map((track) => `<label class="track-title-editor"><span>${String(track.number).padStart(2, '0')}</span><input type="text" data-manual-track="${track.number}" value="${escapeHtml(track.title?.startsWith('Faixa ') ? '' : track.title || '')}" placeholder="Título da faixa ${track.number}"></label>`).join('');
}

function openIdentifyModal() {
  ui.manualArtist.value = state.disc?.artist === 'Artista desconhecido' ? '' : (state.disc?.artist || '');
  ui.manualAlbum.value = state.disc?.album === 'CD de áudio' ? '' : (state.disc?.album || '');
  populateManualTrackTitles();
  openModal(ui.identifyModal);
  setTimeout(() => ui.releaseSearchInput.focus(), 100);
}

async function searchReleases(event) {
  event.preventDefault();
  const query = ui.releaseSearchInput.value.trim();
  if (!query) return;
  ui.releaseResults.innerHTML = '<div class="loading-spinner"></div>';
  try {
    const payload = await api('/api/disc/search', { method: 'POST', body: JSON.stringify({ query }) });
    if (!payload.results.length) {
      ui.releaseResults.innerHTML = '<p class="muted">Nenhum álbum encontrado. Tente apenas o artista ou outro nome do álbum.</p>';
      return;
    }
    ui.releaseResults.innerHTML = payload.results.map((item) => `<article class="release-card ${item.matches_track_count ? 'match' : ''}"><img src="${item.cover_url}" onerror="this.src='/static/img/disc-placeholder.svg'" alt=""><div><strong>${escapeHtml(item.album)}</strong><small>${escapeHtml(item.artist)}</small><small>${escapeHtml([item.date, item.country, item.track_counts?.length ? `${item.track_counts.join('/')} faixas` : ''].filter(Boolean).join(' · '))}</small></div><button class="primary-action choose-release" data-release-id="${item.release_id}" type="button">Usar</button></article>`).join('');
    $$('.choose-release').forEach((button) => button.addEventListener('click', () => chooseRelease(button.dataset.releaseId, button)));
  } catch (error) { ui.releaseResults.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`; }
}

async function chooseRelease(releaseId, button) {
  button.disabled = true; button.textContent = 'Carregando…';
  try {
    await api('/api/disc/select-release', { method: 'POST', body: JSON.stringify({ release_id: releaseId }) });
    closeModal(ui.identifyModal);
    showToast('Álbum associado ao CD. A escolha ficou salva.');
    await refreshDisc();
    if (state.settings.auto_lyrics) loadLyrics(state.currentTrack);
  } catch (error) { showToast(error.message); button.disabled = false; button.textContent = 'Usar'; }
}

async function saveManualMetadata() {
  const titles = $$('[data-manual-track]').map((input) => input.value.trim());
  try {
    await api('/api/disc/custom', { method: 'POST', body: JSON.stringify({ artist: ui.manualArtist.value, album: ui.manualAlbum.value, titles }) });
    closeModal(ui.identifyModal);
    showToast('Informações salvas para este CD.');
    await refreshDisc();
  } catch (error) { showToast(error.message); }
}

async function retryAutomatic() {
  ui.retryAutomaticButton.disabled = true;
  try {
    await api('/api/disc/retry', { method: 'POST' });
    closeModal(ui.identifyModal);
    showToast('Nova busca automática iniciada.');
  } catch (error) { showToast(error.message); }
  finally { ui.retryAutomaticButton.disabled = false; }
}

async function loadSettings() {
  try {
    const payload = await api('/api/settings');
    state.settings = payload;
    ui.musicbrainzContact.value = payload.musicbrainz_contact || '';
    ui.autoLyricsToggle.checked = payload.auto_lyrics;
    setVolumeVisual(Number(payload.default_volume ?? 80));
  } catch (error) { showToast(error.message); }
}

async function saveSettings() {
  ui.saveSettingsButton.disabled = true;
  const body = {
    musicbrainz_contact: ui.musicbrainzContact.value.trim(),
    auto_lyrics: ui.autoLyricsToggle.checked,
    default_volume: Number(ui.volumeRange.value || 80),
  };
  try {
    await api('/api/settings', { method: 'POST', body: JSON.stringify(body) });
    await loadSettings();
    showToast('Configurações salvas. Se houver um CD inserido, uma nova busca foi iniciada.');
  } catch (error) { showToast(error.message); }
  finally { ui.saveSettingsButton.disabled = false; }
}

async function clearCache() {
  if (!confirm('Apagar capas, resultados e associações salvas?')) return;
  try { const result = await api('/api/cache/clear', { method: 'POST' }); showToast(result.message); } catch (error) { showToast(error.message); }
}


function formatListeningTime(seconds) {
  const totalMinutes = Math.max(0, Math.round(Number(seconds || 0) / 60));
  if (totalMinutes < 60) return `${totalMinutes}min`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

function formatArchiveDate(value) {
  if (!value) return 'Ainda não ouvido';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Data indisponível';
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
}

function renderCollection() {
  const collection = state.collection || {};
  const summary = collection.summary || {};
  ui.statAlbums.textContent = Number(summary.albums || 0).toLocaleString('pt-BR');
  ui.statArtists.textContent = Number(summary.artists || 0).toLocaleString('pt-BR');
  ui.statPlays.textContent = Number(summary.plays || 0).toLocaleString('pt-BR');
  ui.statTime.textContent = formatListeningTime(summary.listened_seconds || 0);
  ui.favoriteGenre.textContent = summary.favorite_genre || '—';
  ui.collectionUpdated.textContent = summary.albums ? 'MEMORY ACTIVE' : 'LOCAL MEMORY';

  const genres = collection.genres || [];
  const maxGenre = Math.max(1, ...genres.map((item) => Number(item.albums || 0) + Number(item.plays || 0)));
  ui.genreBars.innerHTML = genres.length ? genres.slice(0, 6).map((item) => {
    const value = Number(item.albums || 0) + Number(item.plays || 0);
    const width = Math.max(7, Math.round((value / maxGenre) * 100));
    return `<div class="genre-row"><span>${escapeHtml(item.genre)}</span><div><i style="--bar:${width}%"></i></div><b>${Number(item.albums || 0)}</b></div>`;
  }).join('') : '<p class="muted">Seu estilo aparecerá conforme os CDs forem catalogados.</p>';

  const artists = collection.top_artists || [];
  ui.topArtists.innerHTML = artists.length ? artists.slice(0, 6).map((item, index) => `
    <div class="top-artist-row"><span>${String(index + 1).padStart(2, '0')}</span><strong>${escapeHtml(item.artist)}</strong><b>${Number(item.plays || 0)}</b></div>`).join('') : '<p class="muted">Nenhuma reprodução registrada.</p>';

  renderCollectionGallery();
}

function renderCollectionGallery() {
  const query = String(ui.collectionSearch?.value || '').trim().toLocaleLowerCase('pt-BR');
  const sort = ui.collectionSort?.value || 'recent';
  let albums = [...(state.collection?.albums || [])];
  if (query) {
    albums = albums.filter((item) => [item.artist, item.album, item.year, ...(item.genres || [])]
      .filter(Boolean).join(' ').toLocaleLowerCase('pt-BR').includes(query));
  }
  albums.sort((a, b) => {
    if (sort === 'played') return Number(b.play_count || 0) - Number(a.play_count || 0) || Number(b.listened_seconds || 0) - Number(a.listened_seconds || 0);
    if (sort === 'artist') return String(a.artist || '').localeCompare(String(b.artist || ''), 'pt-BR');
    if (sort === 'album') return String(a.album || '').localeCompare(String(b.album || ''), 'pt-BR');
    return String(b.last_played || b.last_seen || b.added_at || '').localeCompare(String(a.last_played || a.last_seen || a.added_at || ''));
  });
  ui.collectionCount.textContent = `${albums.length} ${albums.length === 1 ? 'item' : 'itens'}`;
  if (!albums.length) {
    ui.collectionGallery.innerHTML = `<div class="collection-empty"><div class="archive-disc">CD</div><p>${query ? 'Nenhum item corresponde à pesquisa.' : 'Os CDs identificados aparecerão automaticamente nesta galeria.'}</p></div>`;
    return;
  }
  ui.collectionGallery.innerHTML = albums.map((item, index) => `
    <article class="album-archive-card" style="--archive-delay:${Math.min(index * 45, 450)}ms">
      <div class="archive-cover"><img src="${escapeHtml(item.cover_url || '/static/img/disc-placeholder.svg')}" onerror="this.src='/static/img/disc-placeholder.svg'" alt="Capa de ${escapeHtml(item.album)}"><span>${String(item.track_count || 0).padStart(2, '0')} TRK</span></div>
      <div class="archive-card-copy">
        <small>${escapeHtml(item.year || 'ANO —')}</small>
        <strong title="${escapeHtml(item.album)}">${escapeHtml(item.album)}</strong>
        <p title="${escapeHtml(item.artist)}">${escapeHtml(item.artist)}</p>
        <div class="archive-tags">${(item.genres || []).slice(0, 3).map((genre) => `<span>${escapeHtml(genre)}</span>`).join('') || '<span>sem estilo</span>'}</div>
      </div>
      <div class="archive-card-stats"><span><b>${Number(item.play_count || 0)}</b> plays</span><span><b>${formatListeningTime(item.listened_seconds || 0)}</b> ouvidos</span></div>
      <div class="archive-card-foot"><span>Adicionado ${formatArchiveDate(item.added_at)}</span><span>${item.last_played ? `Último play ${formatArchiveDate(item.last_played)}` : 'Ainda não reproduzido'}</span></div>
    </article>`).join('');
}

async function loadCollection() {
  try {
    state.collection = await api('/api/collection');
    renderCollection();
  } catch (error) {
    if (ui.collectionGallery) ui.collectionGallery.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

async function clearCollection() {
  if (!confirm('Apagar a galeria e todas as estatísticas de reprodução?')) return;
  try {
    const result = await api('/api/collection/clear', { method: 'POST' });
    showToast(result.message);
    await loadCollection();
  } catch (error) { showToast(error.message); }
}

let volumeSendTimer;
let volumeDragging = false;
let volumeUnsupportedNotified = false;

function setVolumeVisual(value) {
  const normalized = Math.max(0, Math.min(100, Math.round(Number(value) || 0)));
  ui.volumeRange.value = normalized;
  const angle = -135 + (normalized / 100) * 270;
  ui.volumeKnob.style.setProperty('--knob-angle', `${angle}deg`);
  ui.volumeKnob.setAttribute('aria-valuenow', String(normalized));
  ui.volumeKnob.setAttribute('aria-valuetext', `${normalized}%`);
}

function sendVolume(value) {
  const normalized = Math.max(0, Math.min(100, Math.round(Number(value) || 0)));
  setVolumeVisual(normalized);
  clearTimeout(volumeSendTimer);
  volumeSendTimer = setTimeout(async () => {
    try {
      const result = await api('/api/player/volume', { method: 'POST', body: JSON.stringify({ volume: normalized }) });
      if (result.driver_supported === false && !volumeUnsupportedNotified) {
        volumeUnsupportedNotified = true;
        showToast('O leitor não aceitou volume via MCI. O controle visual continuará salvo; use também o volume do Windows.', 6500);
      }
    } catch (error) { showToast(error.message); }
  }, 80);
}

function volumeFromPointer(event) {
  const rect = ui.volumeKnob.getBoundingClientRect();
  const dx = event.clientX - (rect.left + rect.width / 2);
  const dy = event.clientY - (rect.top + rect.height / 2);
  let angle = Math.atan2(dy, dx) * 180 / Math.PI + 90;
  while (angle > 180) angle -= 360;
  while (angle < -180) angle += 360;
  angle = Math.max(-135, Math.min(135, angle));
  return Math.round(((angle + 135) / 270) * 100);
}

function bindVolumeKnob() {
  ui.volumeKnob.addEventListener('pointerdown', (event) => {
    volumeDragging = true;
    ui.volumeKnob.setPointerCapture(event.pointerId);
    sendVolume(volumeFromPointer(event));
  });
  ui.volumeKnob.addEventListener('pointermove', (event) => {
    if (volumeDragging) sendVolume(volumeFromPointer(event));
  });
  const end = (event) => {
    volumeDragging = false;
    if (ui.volumeKnob.hasPointerCapture?.(event.pointerId)) ui.volumeKnob.releasePointerCapture(event.pointerId);
  };
  ui.volumeKnob.addEventListener('pointerup', end);
  ui.volumeKnob.addEventListener('pointercancel', end);
  ui.volumeKnob.addEventListener('wheel', (event) => {
    event.preventDefault();
    sendVolume(Number(ui.volumeRange.value) + (event.deltaY < 0 ? 4 : -4));
  }, { passive: false });
  ui.volumeKnob.addEventListener('keydown', (event) => {
    if (!['ArrowUp', 'ArrowRight', 'ArrowDown', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const current = Number(ui.volumeRange.value);
    if (event.key === 'Home') sendVolume(0);
    else if (event.key === 'End') sendVolume(100);
    else sendVolume(current + (['ArrowUp', 'ArrowRight'].includes(event.key) ? 3 : -3));
  });
}

async function updatePlaybackOptions() {
  try {
    await api('/api/player/options', {
      method: 'POST',
      body: JSON.stringify({ shuffle: state.shuffle, repeat: state.repeat }),
    });
  } catch (error) { showToast(error.message); }
}

function bindEvents() {
  $$('button').forEach((button) => button.addEventListener('pointerdown', createButtonRipple));
  ui.menuButton.addEventListener('click', () => { ui.drawer.classList.add('open'); ui.drawerBackdrop.classList.add('open'); });
  ui.closeDrawerButton.addEventListener('click', () => { ui.drawer.classList.remove('open'); ui.drawerBackdrop.classList.remove('open'); });
  ui.drawerBackdrop.addEventListener('click', () => ui.closeDrawerButton.click());
  ui.settingsButton.addEventListener('click', async () => { await loadSettings(); openModal(ui.settingsModal); });
  $$('[data-close-modal]').forEach((button) => button.addEventListener('click', () => closeModal($(`#${button.dataset.closeModal}`))));
  $$('.modal-backdrop').forEach((backdrop) => backdrop.addEventListener('click', (event) => { if (event.target === backdrop) closeModal(backdrop); }));
  $$('.panel-tab').forEach((button) => button.addEventListener('click', () => setPanel(button.dataset.panel)));
  $$('.tab-button').forEach((button) => button.addEventListener('click', () => setPanel(button.dataset.tab === 'artist' ? 'artistPanel' : 'tracksPanel')));

  ui.playButton.addEventListener('click', togglePlay); ui.previousButton.addEventListener('click', previousTrack); ui.nextButton.addEventListener('click', nextTrack);
  ui.shuffleButton.addEventListener('click', async () => { state.shuffle = !state.shuffle; ui.shuffleButton.classList.toggle('active', state.shuffle); await updatePlaybackOptions(); showToast(state.shuffle ? 'Modo aleatório ativado.' : 'Modo aleatório desativado.'); });
  ui.repeatButton.addEventListener('click', async () => { state.repeat = state.repeat === 'off' ? 'all' : state.repeat === 'all' ? 'one' : 'off'; ui.repeatButton.classList.toggle('active', state.repeat !== 'off'); ui.repeatLabel.textContent = state.repeat === 'one' ? 'REP 1' : 'REP'; await updatePlaybackOptions(); showToast(state.repeat === 'one' ? 'Repetir faixa ativado.' : state.repeat === 'all' ? 'Repetir CD ativado.' : 'Repetição desativada.'); });
  ui.lyricsQuickButton.addEventListener('click', () => { setPanel('lyricsPanel'); loadLyrics(state.currentTrack); });
  ui.coverImage.addEventListener('error', () => { ui.coverImage.src = '/static/img/disc-placeholder.svg'; });

  ui.progressRange.addEventListener('input', () => { state.seeking = true; ui.elapsedTime.textContent = formatTime(ui.progressRange.value); });
  ui.progressRange.addEventListener('change', async () => { try { await api('/api/player/seek', { method: 'POST', body: JSON.stringify({ seconds: Number(ui.progressRange.value) }) }); } catch (error) { showToast(error.message); } finally { state.seeking = false; } });
  ui.volumeRange.addEventListener('input', () => sendVolume(Number(ui.volumeRange.value)));
  bindVolumeKnob();

  ui.scanButton.addEventListener('click', async () => { try { await api('/api/scan', { method: 'POST' }); showToast('Lendo o CD novamente…'); } catch (error) { showToast(error.message); } });
  ui.ejectButton.addEventListener('click', async () => { try { await api('/api/player/eject', { method: 'POST' }); } catch (error) { showToast(error.message); } });
  ui.driveSelect.addEventListener('change', async () => { if (!ui.driveSelect.value) return; try { await api('/api/drive', { method: 'POST', body: JSON.stringify({ drive: ui.driveSelect.value }) }); } catch (error) { showToast(error.message); } });

  ui.identifyButton.addEventListener('click', openIdentifyModal);
  ui.releaseSearchForm.addEventListener('submit', searchReleases);
  ui.saveManualButton.addEventListener('click', saveManualMetadata);
  ui.retryAutomaticButton.addEventListener('click', retryAutomatic);
  ui.saveSettingsButton.addEventListener('click', saveSettings);
  ui.clearCacheButton.addEventListener('click', clearCache);
  ui.clearCollectionButton.addEventListener('click', clearCollection);
  ui.collectionSearch.addEventListener('input', renderCollectionGallery);
  ui.collectionSort.addEventListener('change', renderCollectionGallery);

  document.addEventListener('keydown', (event) => {
    if (event.target.matches('input, textarea, select')) return;
    if (event.code === 'Space') { event.preventDefault(); togglePlay(); }
    if (event.key === 'ArrowLeft') previousTrack();
    if (event.key === 'ArrowRight') nextTrack();
    if (event.key.toLowerCase() === 'l') { setPanel('lyricsPanel'); loadLyrics(state.currentTrack); }
    if (event.key === 'Escape') { $$('.modal-backdrop.open').forEach(closeModal); }
  });
}

async function init() {
  bindEvents();
  await loadSettings();
  await refreshDisc();
  await refreshPlayerStatus();
  await loadCollection();
  requestAnimationFrame(() => document.body.classList.add('app-ready'));
  setInterval(refreshDisc, 1800);
  setInterval(refreshPlayerStatus, 650);
  setInterval(loadCollection, 12000);
}

document.addEventListener('DOMContentLoaded', init);
