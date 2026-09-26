import * as THREE from 'three';
import {GLTFLoader} from './vendor/GLTFLoader.js';
import {OrbitControls} from './vendor/OrbitControls.js';
const host=document.querySelector('#view'),status=document.querySelector('#status');
try{
 const scene=new THREE.Scene();scene.background=new THREE.Color('#eeeade');
 const camera=new THREE.PerspectiveCamera(38,host.clientWidth/host.clientHeight,.0001,10);
 const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.append(renderer.domElement);
 scene.add(new THREE.HemisphereLight(0xffffff,0x516256,2.4));const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(.1,.2,.1);scene.add(light);
 const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
 const grid=new THREE.GridHelper(.12,12,0x849a8c,0xc9d0c4);scene.add(grid);
 const resize=()=>{renderer.setSize(host.clientWidth,host.clientHeight);camera.aspect=host.clientWidth/host.clientHeight;camera.updateProjectionMatrix()};new ResizeObserver(resize).observe(host);
 new GLTFLoader().load('./alps-rk09l1140a5l.glb',g=>{
  const box=new THREE.Box3().setFromObject(g.scene),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());g.scene.position.sub(center);g.scene.position.y+=size.y/2;scene.add(g.scene);
  controls.target.set(0,size.y/2,0);const d=Math.max(size.x,size.y,size.z)*3.0;camera.position.set(d*.7,d*.65,d);controls.update();
  status.textContent=`Original geometry loaded · ${(size.x*1000).toFixed(2)} × ${(size.y*1000).toFixed(2)} × ${(size.z*1000).toFixed(2)} mm scene bounds · not a mounting-datum guarantee`;
 },undefined,e=>{status.textContent='Model load failed; open the static preview or STEP. '+e.message});
 function frame(){requestAnimationFrame(frame);controls.update();renderer.render(scene,camera)}resize();frame();
}catch(e){status.textContent='WebGL unavailable. Use the static preview/STEP. '+e.message}
