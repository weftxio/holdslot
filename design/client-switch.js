/* HoldSlot client switcher. Shared across console pages.
   Clients + selection persist in localStorage so the choice carries between pages.
   Client name drives the URL slug. */
(function(){
  var KEY_LIST='holdslot_clients', KEY_SEL='holdslot_client';
  function slugify(s){return s.toLowerCase().trim().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');}
  function load(){
    var list;try{list=JSON.parse(localStorage.getItem(KEY_LIST));}catch(e){}
    if(!list||!list.length)list=[{name:'Northwind',slug:'northwind'},{name:'Acme Robotics',slug:'acme-robotics'}];
    return list;
  }
  function persist(list){try{localStorage.setItem(KEY_LIST,JSON.stringify(list));}catch(e){}}
  function getSel(list){var s;try{s=localStorage.getItem(KEY_SEL);}catch(e){}
    if(s&&list.some(function(c){return c.slug===s;}))return s;return list[0].slug;}
  function setSel(slug){try{localStorage.setItem(KEY_SEL,slug);}catch(e){}}

  function init(){
    var sw=document.getElementById('clientSwitch');if(!sw)return;
    var btn=document.getElementById('clientBtn'),menu=document.getElementById('clientMenu'),
        nameEl=document.getElementById('clientName'),slugEl=document.getElementById('clientSlug'),
        avEl=document.getElementById('clientAv');
    var list=load(),sel=getSel(list);
    function current(){return list.filter(function(c){return c.slug===sel;})[0]||list[0];}

    function renderBtn(){
      var c=current();
      nameEl.textContent=c.name;
      slugEl.textContent='holdslot.com/'+c.slug;
      avEl.textContent=c.name.charAt(0).toUpperCase();
      // reflect selected client anywhere it's referenced
      document.querySelectorAll('[data-client-name]').forEach(function(el){el.textContent=c.name;});
    }
    function renderMenu(){
      var html='';
      list.forEach(function(c){
        html+='<button class="client-opt'+(c.slug===sel?' on':'')+'" type="button" data-slug="'+c.slug+'">'+
          '<span class="co-name">'+c.name+'</span><span class="co-slug">/'+c.slug+'</span></button>';
      });
      html+='<div class="client-div"></div>'+
        '<button class="cc-toggle" type="button">＋ Create new client</button>'+
        '<div class="client-create-form">'+
          '<input type="text" placeholder="Client name" maxlength="40" autocomplete="off">'+
          '<div class="cc-slug">URL slug: holdslot.com/<b class="cc-slugval">client</b></div>'+
          '<button class="cc-go" type="button">Create client</button>'+
        '</div>';
      menu.innerHTML=html;
      wire();
    }
    function wire(){
      menu.querySelectorAll('.client-opt').forEach(function(o){
        o.addEventListener('click',function(){sel=o.getAttribute('data-slug');setSel(sel);renderBtn();renderMenu();close();});
      });
      var toggle=menu.querySelector('.cc-toggle'),form=menu.querySelector('.client-create-form'),
          input=form.querySelector('input'),go=form.querySelector('.cc-go'),slugval=form.querySelector('.cc-slugval');
      toggle.addEventListener('click',function(){
        form.classList.toggle('show');
        if(form.classList.contains('show')){input.value='';slugval.textContent='client';input.focus();}
      });
      input.addEventListener('input',function(){slugval.textContent=slugify(input.value)||'client';});
      function create(){
        var nm=input.value.trim();if(!nm)return;
        var sg=slugify(nm)||('client-'+Date.now());
        var base=sg,i=2;while(list.some(function(c){return c.slug===sg;})){sg=base+'-'+i;i++;}
        list.push({name:nm,slug:sg});persist(list);sel=sg;setSel(sel);renderBtn();renderMenu();close();
      }
      go.addEventListener('click',create);
      input.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();create();}});
    }
    function close(){sw.classList.remove('open');}
    btn.addEventListener('click',function(e){e.stopPropagation();sw.classList.toggle('open');});
    document.addEventListener('click',function(e){if(!sw.contains(e.target))close();});
    document.addEventListener('keydown',function(e){if(e.key==='Escape')close();});

    renderBtn();renderMenu();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
