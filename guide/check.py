"""Verify every number the guide quotes. Run: python check.py"""
import random
# 1. worked example node: quality 40, 90.5 deg, 500 mm
q, deg, mm = 40, 90.5, 500
a = round(deg*64); d = round(mm*4)
node = bytes([(q<<2)|(1<<1)|0, ((a&0x7F)<<1)|1, a>>7, d&0xFF, d>>8])
print("node bytes:", node.hex(" ").upper(), "angle_q6", a, "dist_q2", d)
b = node
assert (b[0]&1)!=((b[0]>>1)&1) and b[1]&1==1
assert ((b[2]<<7)|(b[1]>>1))/64==deg and (b[3]|b[4]<<8)/4==mm and b[0]>>2==q
# 2. false-lock rate of the 2-bit sync check, with and without the angle check
random.seed(1); N=200000; p2=p3=0
for _ in range(N):
    w=[random.randrange(256) for _ in range(5)]
    ok=(w[0]&1)!=((w[0]>>1)&1) and (w[1]&1)==1
    p2+=ok; p3+=ok and ((w[2]<<7)|(w[1]>>1))<360*64
print("sync only: 1 in %.1f ; with angle check: 1 in %.1f ; 3 in a row: 1 in %.0f"%(N/p2,N/p3,(N/p3)**3))
# 3. numbers
print("FIFO time ms", 16*10/115200*1000, " byte rate", 115200/10, " period clocks", 100_000_000//24000)
for duty in (64,120,128,192): print("duty",duty,"high clocks",duty*4166>>8,"=%.1f%%"%(100*(duty*4166>>8)/4166))
print("ring: 4096 B at 115200 = %.0f ms"%(4096*10/115200*1000), " frame chars", 2+ 4+1+3+1+4+1+4+1+360*4)
print("deg/step 120:",360/312,"  rev time ms @6.35Hz",1000/6.35)
