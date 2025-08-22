(function () {
  if (document.getElementById('bcm-enroll-fab')) return;
  var a = document.createElement('a');
  a.id = 'bcm-enroll-fab';
  a.href = 'https://bcm-demo.onrender.com/static/enroll.html';
  a.target = '_blank';
  a.rel = 'noopener';
  a.textContent = 'Click To Enroll';
  // append when page fully loaded so it layers above other widgets
  if (document.readyState === 'complete') document.body.appendChild(a);
  else window.addEventListener('load', function(){ document.body.appendChild(a); });
})();
