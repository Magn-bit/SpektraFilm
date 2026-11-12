package com.spektra.film;

import java.io.IOException;
import java.io.OutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileInputStream;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/** Baseline RGB TIFF, written one row at a time with an embedded ICC profile. */
public final class TiffEncoder {
    private TiffEncoder() {}
    @FunctionalInterface public interface RowReader { void read(int y, int[] pixels); }
    @FunctionalInterface public interface ShortRowReader { void read(int y, short[] pixels); }

    /** Real unsigned RGB16, lossless Deflate. Only one row is held by the writer. */
    public static void write16(OutputStream target,int width,int height,byte[] icc,ShortRowReader reader) throws IOException {
        write16(target,width,height,icc,null,reader);
    }
    public static void write16(OutputStream target,int width,int height,byte[] icc,File directory,ShortRowReader reader) throws IOException {
        if(width<=0 || height<=0 || width>Integer.MAX_VALUE/6 || icc==null || icc.length<128)throw new IllegalArgumentException("Invalid TIFF dimensions/profile");
        File spool=File.createTempFile("spektra-tiff16-", ".deflate",directory);
        try {
            Deflater deflater=new Deflater(1);
            try(DeflaterOutputStream compressed=new DeflaterOutputStream(new FileOutputStream(spool),deflater,65536)) {
                short[] pixels=new short[width*3];byte[] row=new byte[width*6];
                for(int y=0;y<height;y++) {
                    if(Thread.currentThread().isInterrupted())throw new IOException("TIFF export interrupted");
                    reader.read(y,pixels);
                    for(int c=0;c<pixels.length;c++){row[c*2]=(byte)pixels[c];row[c*2+1]=(byte)(pixels[c]>>>8);}
                    compressed.write(row);
                }
            } finally {deflater.end();}
            final int entries=16,bitsOffset=8+2+entries*12+4;
            final int xResolution=bitsOffset+6,yResolution=xResolution+8,profileOffset=yResolution+8;
            final long dataOffset=(profileOffset+(long)icc.length+1)&~1L;
            if(dataOffset+spool.length()>0xffffffffL)throw new IOException("TIFF exceeds 4 GiB");
            ByteBuffer h=ByteBuffer.allocate((int)dataOffset).order(ByteOrder.LITTLE_ENDIAN);
            h.put((byte)'I').put((byte)'I').putShort((short)42).putInt(8).putShort((short)entries);
            entry(h,256,4,1,width);entry(h,257,4,1,height);entry(h,258,3,3,bitsOffset);entry(h,259,3,1,8);
            entry(h,262,3,1,2);entry(h,273,4,1,dataOffset);entry(h,274,3,1,1);entry(h,277,3,1,3);
            entry(h,278,4,1,height);entry(h,279,4,1,spool.length());entry(h,282,5,1,xResolution);entry(h,283,5,1,yResolution);
            entry(h,284,3,1,1);entry(h,296,3,1,2);entry(h,339,3,1,1);entry(h,34675,7,icc.length,profileOffset);
            h.putInt(0).putShort((short)16).putShort((short)16).putShort((short)16);
            h.putInt(72).putInt(1).putInt(72).putInt(1).put(icc);target.write(h.array());
            try(FileInputStream input=new FileInputStream(spool)){byte[] buffer=new byte[65536];int n;while((n=input.read(buffer))!=-1)target.write(buffer,0,n);}
        } finally {spool.delete();}
    }

    public static void write(OutputStream target, int width, int height, byte[] icc, RowReader reader) throws IOException {
        if (width <= 0 || height <= 0 || icc == null || icc.length < 128) throw new IllegalArgumentException("Invalid TIFF dimensions/profile");
        final int entries = 15;
        final int bitsOffset = 8 + 2 + entries * 12 + 4;
        final int xResolution = bitsOffset + 6;
        final int yResolution = xResolution + 8;
        final int profileOffset = yResolution + 8;
        final long dataOffset = (profileOffset + (long)icc.length + 1) & ~1L;
        final long pixelBytes = (long)width * height * 3;
        if (dataOffset + pixelBytes > 0xffffffffL || dataOffset > Integer.MAX_VALUE || width > Integer.MAX_VALUE/3) throw new IllegalArgumentException("TIFF is too large");
        ByteBuffer header = ByteBuffer.allocate((int)dataOffset).order(ByteOrder.LITTLE_ENDIAN);
        header.put((byte)'I').put((byte)'I').putShort((short)42).putInt(8).putShort((short)entries);
        entry(header,256,4,1,width); entry(header,257,4,1,height);
        entry(header,258,3,3,bitsOffset); entry(header,259,3,1,1);
        entry(header,262,3,1,2); entry(header,273,4,1,dataOffset);
        entry(header,274,3,1,1); entry(header,277,3,1,3);
        entry(header,278,4,1,height); entry(header,279,4,1,pixelBytes);
        entry(header,282,5,1,xResolution); entry(header,283,5,1,yResolution);
        entry(header,284,3,1,1); entry(header,296,3,1,2);
        entry(header,34675,7,icc.length,profileOffset);
        header.putInt(0).putShort((short)8).putShort((short)8).putShort((short)8);
        header.putInt(72).putInt(1).putInt(72).putInt(1).put(icc);
        target.write(header.array());
        int[] pixels = new int[width]; byte[] row = new byte[width*3];
        for (int y=0;y<height;y++) {
            if (Thread.currentThread().isInterrupted()) throw new IOException("TIFF export interrupted");
            reader.read(y,pixels);
            for (int x=0;x<width;x++) {
                row[x*3]=(byte)(pixels[x]>>>16); row[x*3+1]=(byte)(pixels[x]>>>8); row[x*3+2]=(byte)pixels[x];
            }
            target.write(row);
        }
    }
    private static void entry(ByteBuffer buffer,int tag,int type,long count,long value) {
        buffer.putShort((short)tag).putShort((short)type).putInt((int)count).putInt((int)value);
    }
}
