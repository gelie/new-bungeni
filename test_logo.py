from graphviz import Digraph
g = Digraph(format='dot')
g.attr('node', shape='none')
g.node('logo', image='/home/admgelie/Projects/pwms/parliament-logo.png', width='1', height='1', fixedsize='true')
g.render('out')
