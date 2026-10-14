(() => {
 const field=document.getElementById('merch-piece');
 document.querySelectorAll('[data-merch]').forEach(a=>a.addEventListener('click',()=>{field.value=a.dataset.merch;}));
 document.getElementById('merch-interest').addEventListener('submit',e=>{
  e.preventDefault();const d=new FormData(e.currentTarget);
  const body=['Kong merchandise interest — not an order','Name: '+d.get('name'),'Email: '+d.get('email'),'Interested in: '+d.get('piece'),'Size: '+(d.get('size')||'Not specified'),'Approximate quantity: '+(d.get('quantity')||'Not specified'),'Notes: '+(d.get('notes')||'')].join('\n');
  location.href='mailto:info@kongtractors.com?subject='+encodeURIComponent('Kong Merch — '+d.get('piece'))+'&body='+encodeURIComponent(body);
  document.getElementById('merch-form-status').textContent='Email draft requested. Please review and send it in your email app. Nothing has been submitted through this page.';
 });
})();