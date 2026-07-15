(() => {
  const parts = location.pathname.split('/').filter(Boolean);
  const ownerFromHost = location.hostname.endsWith('.github.io')
    ? location.hostname.split('.')[0]
    : 'ricardobmuller';
  const repositoryFromPath = parts[0] || 'AuraCD';
  const owner = ownerFromHost || 'ricardobmuller';
  const repository = repositoryFromPath || 'AuraCD';
  const filename = 'AuraCD-Setup.exe';
  const downloadUrl = `https://github.com/${owner}/${repository}/releases/latest/download/${filename}`;

  document.querySelectorAll('.download-link').forEach((link) => {
    link.href = downloadUrl;
  });

  const status = document.getElementById('release-status');
  fetch(`https://api.github.com/repos/${owner}/${repository}/releases/latest`, {
    headers: { Accept: 'application/vnd.github+json' }
  })
    .then((response) => {
      if (!response.ok) throw new Error('release unavailable');
      return response.json();
    })
    .then((release) => {
      const asset = (release.assets || []).find((item) => item.name === filename);
      const size = asset ? ` · ${(asset.size / 1024 / 1024).toFixed(1)} MB` : '';
      status.textContent = `Versão ${String(release.tag_name || '').replace(/^v/, '')}${size} · Windows 10/11`;
    })
    .catch(() => {
      status.textContent = 'Versão mais recente · Windows 10/11';
    });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });

  document.querySelectorAll('.reveal').forEach((element) => observer.observe(element));
})();
