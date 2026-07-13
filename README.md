Problem
In Thermo Fisher raw files there are two fields for precursor information, i.e., the 
'isolation window target m/z' and the 'selected ion m/z'. 
Those sometimes have different values although they should be the same (see Problem.png)
This script fixes these problems by setting the incorrect value of 'selected ion m/z' to
that of 'isolation window target m/z'. 


1. Read this document!

2. Copy the entire folder to the path where the raw files to be converted are located. 
   The structure should be 
```
   folder
     +- raw-file1.raw
     +- raw-file2.raw
     +- ...
     +- raw-filen.raw
     +- folder
          +- raw-filex.raw
     +- convert2RAW
          +- run.bat
```

3. Double-click the file "run.bat" to start the app

4. Follow the instructions in the terminal.

5. Wait until finished

6. The converted mzML files will be located in the folder mzMLs



Note
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, 
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR 
PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE 
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, 
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE 
OR OTHER DEALINGS IN THE SOFTWARE.