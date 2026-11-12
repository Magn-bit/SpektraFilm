import com.spektra.film.TiffEncoder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.OutputStream;

public class TiffRoundtrip {
    public static void main(String[] args) throws Exception {
        byte[] profile=Files.readAllBytes(Path.of(args[0]));
        try(OutputStream stream=Files.newOutputStream(Path.of(args[1]))) {
            TiffEncoder.write16(stream,17,11,profile,(y,row)-> {
                for(int x=0;x<17;x++) {row[x*3]=(short)(x*3711+y);row[x*3+1]=(short)(y*5821+x);row[x*3+2]=(short)((x^y)*2001+11);}
            });
        }
        try { TiffEncoder.write(OutputStream.nullOutputStream(),0,11,profile,(y,row)->{});throw new AssertionError("Invalid dimensions accepted"); }
        catch(IllegalArgumentException expected) {}
        try { TiffEncoder.write(OutputStream.nullOutputStream(),100000,100000,profile,(y,row)->{});throw new AssertionError("Overflow accepted"); }
        catch(IllegalArgumentException expected) {}
    }
}
