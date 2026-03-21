const { spawn } = require('child_process');
const { chromium } = require('playwright');
const path = require('path');
const repId = 'CA4E6FAF-ECE2-4FDD-BF59-3CF3E486E7AF';
const workdir = path.join('C:', 'Users', 'Kush', 'Desktop', 'amw_analytics');
const pyCmd = `import os\nos.chdir(r"${workdir}")\nos.environ['SECRET_KEY']='devkey'\nfrom app import create_app\napp=create_app()\napp.config.update(LOGIN_DISABLED=True, WTF_CSRF_ENABLED=False)\napp.run(port=5001, use_reloader=False)`;
const py = spawn('python', ['-c', pyCmd], { env: { ...process.env, SECRET_KEY: 'devkey', FLASK_ENV: 'development' }, cwd: workdir, stdio: ['ignore', 'pipe', 'pipe'], shell: true });
py.stdout.on('data', (d)=> console.log('PYOUT', d.toString()))
py.stderr.on('data', (d)=> console.log('PYERR', d.toString()))
(async() => {
  await new Promise(r => setTimeout(r, 5000));
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('console', msg => console.log('BROWSER', msg.type(), msg.text()));
  await page.goto(`http://127.0.0.1:5001/salesreps/${repId}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await browser.close();
  py.kill('SIGINT');
})();
