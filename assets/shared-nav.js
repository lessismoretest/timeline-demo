(function () {
  const navItems = [
    { id: 'mind-map', label: '思维图谱', href: '/mind-map.html' },
    { id: 'matrix', label: '矩阵', href: '/matrix.html' },
    { id: 'timeline', label: '时间线', href: '/vis-timeline.html' },
    { id: 'data', label: 'Data', href: '/data.html' },
    { id: 'brand-wall', label: '图片墙', href: '/brand-wall.html' },
    { id: '3d-camera', label: '3D 视角相机', href: '/camera-3d.html' },
    { id: 'think-different', label: 'Think different', href: '/think-different.html' },
    { id: 'awesome', label: 'Awesome Something', href: '/awesome.html' }
  ];

  function renderNav(activePage) {
    const header = document.createElement('header');
    header.className = 'site-nav';
    header.innerHTML = `
      <a class="site-nav__brand" href="/">taste2</a>
      <nav class="site-nav__tabs" aria-label="主导航">
        ${navItems.map((item) => {
          const activeClass = item.id === activePage ? ' is-active' : '';
          return `<a class="site-nav__tab${activeClass}" href="${item.href}">${item.label}</a>`;
        }).join('')}
      </nav>
    `;
    return header;
  }

  function renderPageHeader(title, subtitle) {
    const wrap = document.createElement('section');
    wrap.className = 'page-shell';
    wrap.innerHTML = `
      <div class="page-shell__header">
        <div>
          <h1 class="page-shell__title">${title}</h1>
          ${subtitle ? `<p class="page-shell__subtitle">${subtitle}</p>` : ''}
        </div>
      </div>
    `;
    return wrap;
  }

  function setupAutoHideNav(header) {
    const root = document.documentElement;
    let hidden = false;
    let lastScrollY = window.scrollY || 0;
    let ticking = false;

    function syncNavMetrics() {
      const height = Math.ceil(header.getBoundingClientRect().height);
      const visibleOffset = hidden ? 0 : height;
      root.style.setProperty('--shared-nav-height', `${height}px`);
      root.style.setProperty('--shared-nav-visible-offset', `${visibleOffset}px`);
      window.dispatchEvent(new CustomEvent('shared-nav-statechange', {
        detail: { hidden, height, visibleOffset }
      }));
    }

    function setHidden(nextHidden) {
      if (hidden === nextHidden) {
        syncNavMetrics();
        return;
      }
      hidden = nextHidden;
      header.classList.toggle('is-hidden', hidden);
      syncNavMetrics();
    }

    function updateOnScroll() {
      ticking = false;
      const currentScrollY = window.scrollY || 0;
      const delta = currentScrollY - lastScrollY;

      if (currentScrollY <= 8) {
        setHidden(false);
        lastScrollY = currentScrollY;
        return;
      }

      if (Math.abs(delta) < 6) {
        return;
      }

      if (delta > 0 && currentScrollY > header.offsetHeight + 24) {
        setHidden(true);
      } else if (delta < 0) {
        setHidden(false);
      }

      lastScrollY = currentScrollY;
    }

    syncNavMetrics();
    window.addEventListener('resize', syncNavMetrics);
    window.addEventListener('scroll', () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(updateOnScroll);
    }, { passive: true });
  }

  window.addEventListener('DOMContentLoaded', () => {
    const activePage = document.body.dataset.navPage || '';
    const mount = document.querySelector('[data-shared-nav-root]');
    const header = renderNav(activePage);
    if (mount) {
      mount.replaceWith(header);
    } else {
      document.body.prepend(header);
    }
    setupAutoHideNav(header);

    const title = document.body.dataset.pageTitle || '';
    const subtitle = document.body.dataset.pageSubtitle || '';
    const pageHeaderMount = document.querySelector('[data-shared-page-header-root]');
    if (pageHeaderMount && title) {
      pageHeaderMount.replaceWith(renderPageHeader(title, subtitle));
    }
  });
})();
