// Nominal ergonomic envelopes only. NOT exact parts, a routed PCB or drill drawing.
// Units mm. No holes are cut because final module/shaft/pad geometry is unqualified.
$fn=40;
color([0.3,0.4,0.4]) cube([250,180,1.6]);
color([0.15,0.2,0.2]) translate([96.4,47,14])cube([57.2,86,4]);
for(side=[0:1])for(row=[0:4]){
  x=side==0?48:202; y=43+row*23.5;
  color([0.25,0.25,0.25]) translate([x,y,12]) cylinder(h=14,r=8);
  color([0.55,0.55,0.55]) translate([side==0?70:166,y-3,11])cube([14,6,5]);
}
// The actual pot manufacturer STEP remains under reference/assets/pot/.
