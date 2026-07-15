(() => {
  const owner = 'ricardobmuller';
  const repository = 'AuraCD';
  const filename = 'AuraCD-Setup.exe';
  const releasePage = `https://github.com/${owner}/${repository}/releases/latest`;
  const fallbackDownload = `https://github.com/${owner}/${repository}/releases/latest/download/${filename}`;

  const bootScreen = document.getElementById('boot-screen');
  window.addEventListener('load', () => {
    window.setTimeout(() => bootScreen?.classList.add('off'), 750);
  });
  window.setTimeout(() => bootScreen?.classList.add('off'), 2200);

  const downloadLinks = [...document.querySelectorAll('.download-link')];
  downloadLinks.forEach((link) => {
    link.href = fallbackDownload;
    link.setAttribute('download', filename);
  });

  const releasePageLink = document.getElementById('release-page-link');
  if (releasePageLink) releasePageLink.href = releasePage;

  const releaseLabel = document.getElementById('release-label');
  const footerReleaseLabel = document.getElementById('footer-release-label');

  fetch(`https://api.github.com/repos/${owner}/${repository}/releases/latest`, {
    headers: { Accept: 'application/vnd.github+json' }
  })
    .then((response) => {
      if (!response.ok) throw new Error('Não foi possível consultar a Release');
      return response.json();
    })
    .then((release) => {
      const asset = (release.assets || []).find((item) => item.name === filename);
      const version = String(release.tag_name || '').replace(/^v/, '') || 'mais recente';
      const size = asset?.size ? `${(asset.size / 1024 / 1024).toFixed(1)} MB` : '';
      const label = `Versão ${version}${size ? ` · ${size}` : ''}`;
      if (releaseLabel) releaseLabel.textContent = label;
      if (footerReleaseLabel) footerReleaseLabel.textContent = `${label} · Windows 10/11`;
      if (asset?.browser_download_url) {
        downloadLinks.forEach((link) => {
          link.href = asset.browser_download_url;
          link.removeAttribute('download');
        });
      }
    })
    .catch(() => {
      if (releaseLabel) releaseLabel.textContent = 'Versão mais recente · Windows 10/11';
      if (footerReleaseLabel) footerReleaseLabel.textContent = 'Versão mais recente · Windows 10/11';
    });

  downloadLinks.forEach((link) => {
    link.addEventListener('click', () => {
      link.classList.add('downloading');
      const copy = link.querySelector('.primary-download-copy small');
      if (copy) copy.textContent = 'Iniciando download…';
      window.setTimeout(() => link.classList.remove('downloading'), 1300);
    });
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.13 });
  document.querySelectorAll('.reveal').forEach((element) => observer.observe(element));

  const playButton = document.getElementById('demo-play');
  const demoTrack = document.getElementById('demo-track');
  const demoTime = document.getElementById('demo-time');
  let demoPlaying = true;
  let demoSeconds = 0;

  playButton?.addEventListener('click', () => {
    demoPlaying = !demoPlaying;
    playButton.firstChild.textContent = demoPlaying ? '▶' : '■';
    document.querySelector('.disc-visual')?.style.setProperty('animation-play-state', demoPlaying ? 'running' : 'paused');
    document.querySelectorAll('.equalizer i').forEach((bar) => {
      bar.style.animationPlayState = demoPlaying ? 'running' : 'paused';
    });
  });

  window.setInterval(() => {
    if (!demoPlaying) return;
    demoSeconds += 1;
    if (demoSeconds >= 267) {
      demoSeconds = 0;
      const next = (Number(demoTrack?.textContent || 1) % 12) + 1;
      if (demoTrack) demoTrack.textContent = String(next).padStart(2, '0');
    }
    const minutes = Math.floor(demoSeconds / 60);
    const seconds = demoSeconds % 60;
    if (demoTime) demoTime.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }, 1000);

  const knob = document.getElementById('volume-knob');
  const ledContainer = document.getElementById('volume-leds');
  let visualVolume = 68;

  if (ledContainer) {
    for (let i = 0; i < 5; i += 1) ledContainer.appendChild(document.createElement('i'));
  }

  function renderVolume() {
    const angle = -125 + (visualVolume / 100) * 250;
    if (knob) {
      knob.style.transform = `rotate(${angle}deg)`;
      knob.setAttribute('aria-valuenow', String(visualVolume));
    }
    ledContainer?.querySelectorAll('i').forEach((led, index) => {
      led.classList.toggle('on', visualVolume >= (index + 1) * 18);
    });
  }

  function setVolumeFromPointer(event) {
    if (!knob) return;
    const rect = knob.getBoundingClientRect();
    const x = event.clientX - (rect.left + rect.width / 2);
    const y = event.clientY - (rect.top + rect.height / 2);
    let angle = Math.atan2(y, x) * (180 / Math.PI) + 90;
    if (angle < -180) angle += 360;
    angle = Math.max(-125, Math.min(125, angle));
    visualVolume = Math.round(((angle + 125) / 250) * 100);
    renderVolume();
  }

  knob?.addEventListener('pointerdown', (event) => {
    knob.setPointerCapture(event.pointerId);
    setVolumeFromPointer(event);
  });
  knob?.addEventListener('pointermove', (event) => {
    if (knob.hasPointerCapture(event.pointerId)) setVolumeFromPointer(event);
  });
  knob?.addEventListener('wheel', (event) => {
    event.preventDefault();
    visualVolume = Math.max(0, Math.min(100, visualVolume + (event.deltaY < 0 ? 4 : -4)));
    renderVolume();
  }, { passive: false });
  knob?.addEventListener('keydown', (event) => {
    if (!['ArrowUp', 'ArrowRight', 'ArrowDown', 'ArrowLeft'].includes(event.key)) return;
    event.preventDefault();
    visualVolume = Math.max(0, Math.min(100, visualVolume + (['ArrowUp', 'ArrowRight'].includes(event.key) ? 4 : -4)));
    renderVolume();
  });
  renderVolume();
})();
