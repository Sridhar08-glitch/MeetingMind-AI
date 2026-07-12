/**
 * Inline, render-blocking script that sets the `dark` class on <html> before the
 * app paints — avoids a flash of the wrong theme. Reads the same localStorage key
 * the Zustand theme store persists to ("meetingmind-theme").
 */
const CODE = `(function(){try{var r=localStorage.getItem('meetingmind-theme');var t=r?(JSON.parse(r).state||{}).theme:'system';if(!t)t='system';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);if(d)document.documentElement.classList.add('dark');}catch(e){}})();`;

export function ThemeScript() {
  return <script dangerouslySetInnerHTML={{ __html: CODE }} />;
}
